import tempfile
import unittest
from pathlib import Path
from PIL import Image
from happytrip_runtime.adapters.mock import MockAdapter
from happytrip_runtime.adapters.host import HostAdapter
from happytrip_runtime.runner import (run_job, prepare_job, read_json, reserve_stage,
    record_failure, import_candidate, finalize_job, cancel_job, digest)
from happytrip_runtime.types import HappyTripError
from happytrip_runtime.compositor import compose
from happytrip_runtime.runner import write_json


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.photo = self.root / "input.png"
        Image.new("RGB", (120, 80), "green").save(self.photo)
        self.job = self.root / "job"
        self.request = {"mode": "B04", "photos": [{"photo_id": "p1", "ref": str(self.photo), "roles": ["scene"]}]}
        self.adapter = MockAdapter()

    def tearDown(self):
        self.tmp.cleanup()

    def stage(self):
        return next(s["id"] for s in read_json(self.job / "plan.json")["stages"] if s["kind"] == "generate")

    def test_mock_is_not_final_and_resume_does_not_recall(self):
        result = run_job(self.request, self.adapter, self.job)
        self.assertEqual(result["image_calls"], 1)
        self.assertEqual(result["image_assets"], [])
        self.assertEqual(result["validation_status"], "not_run")
        self.assertTrue(result["candidate_assets"][0]["simulated"])
        again = run_job(self.request, self.adapter, self.job)
        self.assertEqual(again["image_calls"], 1)
        with self.assertRaises(HappyTripError):
            finalize_job(self.job, result["candidate_assets"][0]["path"], {})

    def test_unknown_does_not_retry(self):
        prepare_job(self.request, self.adapter, self.job)
        reserve_stage(self.job, self.stage())
        record_failure(self.job, self.stage(), "unknown")
        with self.assertRaises(HappyTripError) as cm:
            reserve_stage(self.job, self.stage())
        self.assertEqual(cm.exception.code, "CALL_STATUS_UNKNOWN")
        result = run_job(self.request, self.adapter, self.job)
        self.assertEqual(result["image_calls"], 1)

    def test_cancel_and_changed_request_refused(self):
        prepare_job(self.request, self.adapter, self.job)
        cancel_job(self.job)
        with self.assertRaises(HappyTripError):
            reserve_stage(self.job, self.stage())
        with self.assertRaises(HappyTripError):
            prepare_job({**self.request, "mode": "A05"}, self.adapter, self.job)

    def test_budget_stops_repair(self):
        self.request["budget"] = {"max_image_calls": 1, "max_repairs_per_stage": 1}
        prepare_job(self.request, self.adapter, self.job)
        reserve_stage(self.job, self.stage())
        record_failure(self.job, self.stage(), "failed")
        with self.assertRaises(HappyTripError) as cm:
            reserve_stage(self.job, self.stage())
        self.assertEqual(cm.exception.code, "BUDGET_EXCEEDED")

    def test_no_capabilities_is_prompt_only(self):
        result = prepare_job(self.request, HostAdapter(), self.job)
        self.assertEqual(result["status"], "prompt_only")
        self.assertEqual(result["image_assets"], [])

    def test_host_handoff_does_not_count_an_unmade_call(self):
        result = run_job(self.request, HostAdapter(self.adapter.capabilities()), self.job)
        self.assertEqual(result["status"], "prompt_only")
        self.assertEqual(result["image_calls"], 0)

    def test_repair_preserves_call_receipts(self):
        prepare_job(self.request, self.adapter, self.job)
        sid = self.stage()
        reserve_stage(self.job, sid)
        import_candidate(self.job, sid, self.photo, actual_cost=0.2, provider_request_id="first")
        record_failure(self.job, sid, "failed")
        reserve_stage(self.job, sid)
        result = import_candidate(self.job, sid, self.photo, actual_cost=0.3, provider_request_id="repair")
        self.assertEqual(result["actual_cost"], 0.5)
        self.assertEqual(result["provider_request_ids"], ["first", "repair"])
        self.assertEqual(len(read_json(self.job / "state.json")["call_history"]), 2)

    def test_missing_asset_no_calls(self):
        self.request["photos"][0]["ref"] = str(self.root / "missing.png")
        result = prepare_job(self.request, self.adapter, self.job)
        self.assertEqual(result["status"], "needs_input")
        self.assertEqual(result["image_calls"], 0)

    def test_import_requires_reservation_and_review_exact_hash(self):
        prepare_job(self.request, self.adapter, self.job)
        sid = self.stage()
        with self.assertRaises(HappyTripError):
            import_candidate(self.job, sid, self.photo)
        reserve_stage(self.job, sid)
        import_candidate(self.job, sid, self.photo)
        review = {"reviewer": "synthetic pipeline test", "image_sha256": "wrong", "visual_status": "pass",
                  "checks": [{"name": n, "status": "pass", "reason": "synthetic control-flow fixture; no real photo validation"}
                             for n in ("mode_visual", "identity_and_subjects", "facts_and_text", "edit_scope")]}
        with self.assertRaises(HappyTripError):
            finalize_job(self.job, self.photo, review)
        review["image_sha256"] = digest(self.photo)
        result = finalize_job(self.job, self.photo, review)
        self.assertEqual(result["status"], "succeeded")
        self.assertTrue(Path(result["image_assets"][0]["path"]).is_file())

    def test_secret_never_persisted(self):
        self.request["api_key"] = "do-not-write"
        with self.assertRaises(HappyTripError):
            prepare_job(self.request, self.adapter, self.job)
        self.assertFalse((self.job / "request.json").exists())

    def test_one_heuristic_suggestion_does_not_authorize_generation(self):
        self.request["mode"] = "auto"
        self.request["photos"].append({"photo_id": "p2", "ref": str(self.photo), "roles": ["scene"]})
        result = prepare_job(self.request, self.adapter, self.job)
        self.assertEqual(result["status"], "needs_input")
        self.assertEqual(result["image_calls"], 0)
        self.assertEqual(result["errors"][0]["code"], "MODE_SELECTION_REQUIRED")

    def test_repair_keeps_other_comic_panels(self):
        self.request["mode"] = "B16"
        self.request["photos"][0]["roles"] = ["person", "scene"]
        self.request["mode_options"] = {"panel_count": 3, "story_basis": "user_provided", "panels": [
            {"index": i, "action": f"用户确认动作 {i}", "photo_ids": ["p1"], "dialogue": "", "basis": "user"}
            for i in range(1, 4)]}
        result = run_job(self.request, self.adapter, self.job)
        self.assertEqual(result["image_calls"], 3)
        original = read_json(self.job / "state.json")["stages"]
        ids = list(original)
        record_failure(self.job, ids[1], "failed")
        call = reserve_stage(self.job, ids[1])
        candidate = self.adapter.execute(call)
        import_candidate(self.job, ids[1], candidate["path"], simulated=True)
        state = read_json(self.job / "state.json")
        self.assertEqual(state["image_calls"], 4)
        self.assertEqual(state["stages"][ids[0]], original[ids[0]])
        self.assertEqual(state["stages"][ids[2]], original[ids[2]])

    def test_composed_b01_finalizes_with_actual_manifest(self):
        self.request["mode"] = "B01"
        prepare_job(self.request, self.adapter, self.job)
        reserve_stage(self.job, self.stage())
        souvenir = self.root / "synthetic-souvenir.png"
        Image.new("RGBA", (100, 80), "orange").save(souvenir)
        imported = import_candidate(self.job, self.stage(), souvenir)
        candidate = imported["candidate_assets"][0]["path"]
        asset = read_json(self.job / "assets.json")[0]
        composed = compose(asset, [{"path": candidate, "box": [.1, .05, .8, .4]}],
                           {"kind": "B01", "size": [300, 400], "output_path": str(self.root / "poster.png")}, {})
        manifest = self.root / "poster.json"
        write_json(manifest, composed)
        review = {"reviewer": "synthetic integration fixture", "image_sha256": composed["sha256"], "visual_status": "pass",
                  "composition_manifest": str(manifest), "checks": [
                      {"name": n, "status": "pass", "reason": "synthetic fixture proves control flow only"}
                      for n in ("mode_visual", "identity_and_subjects", "facts_and_text", "edit_scope")]}
        # A mismatched original reference is rejected even when the picture hash matches.
        tampered = read_json(manifest)
        next(p for p in tampered["provenance"] if p["kind"] == "source_photo")["photo_id"] = "unrelated"
        write_json(manifest, tampered)
        with self.assertRaises(HappyTripError):
            finalize_job(self.job, composed["path"], review)
        write_json(manifest, composed)
        result = finalize_job(self.job, composed["path"], review)
        self.assertEqual(result["status"], "succeeded")
        with Image.open(result["image_assets"][0]["path"]) as output:
            self.assertEqual(output.format, "PNG")
            self.assertFalse(output.getexif())
