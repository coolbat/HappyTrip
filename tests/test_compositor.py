import json
import os
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

from happytrip_runtime.assets import resolve_assets, sha256_file
from happytrip_runtime.compositor import compose, verify_protected_pixels
from happytrip_runtime.export import export_result
from happytrip_runtime.types import HappyTripError
from happytrip_runtime.validator import validate_image_file, validate_result


class CompositorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.image("source.png", (20, 12), "#184453")
        self.candidate = self.image("candidate.png", (20, 12), "#ee9333")
        self.asset = resolve_assets({"photos": [{"photo_id": "p01", "ref": self.source, "roles": ["base"]}]}, workdir=self.root / "work")[0]
        self.mask = self.root / "mask.png"
        mask = Image.new("L", (20, 12), 0)
        ImageDraw.Draw(mask).rectangle((5, 2, 10, 9), fill=255)
        mask.putpixel((4, 4), 80)
        mask.save(self.mask)

    def tearDown(self):
        self.temp.cleanup()

    def image(self, name, size, color, mode="RGB"):
        path = self.root / name
        Image.new(mode, size, color).save(path)
        return str(path)

    def layout(self, kind, **overrides):
        return {"kind": kind, "output_path": str(self.root / "result.png"), **overrides}

    def masked(self, **contract):
        return compose(self.asset, [{"path": self.candidate, "mask_path": str(self.mask)}], self.layout("masked_edit"), contract)

    def test_masked_edit_preserves_all_unpermitted_pixels(self):
        result = self.masked()
        self.assertEqual(result["checks"][0]["changed_pixels"], 0)
        self.assertEqual(result["validation"]["status"], "pass")
        self.assertEqual(result["visual_review"], "not_run")
        with Image.open(result["path"]) as output, Image.open(self.source) as source:
            self.assertEqual(output.getpixel((0, 0))[:3], source.getpixel((0, 0)))
            self.assertNotEqual(output.getpixel((6, 4))[:3], source.getpixel((6, 4)))
        check = verify_protected_pixels(self.source, self.candidate, str(self.mask))
        self.assertEqual(check["status"], "fail")

    def test_feather_must_be_inside_allowed_region(self):
        with self.assertRaisesRegex(HappyTripError, "feathering"):
            self.masked(allowed_regions=[[.25, 0, .5, 1]])

    def test_wrong_canvas_and_protected_overlap_fail(self):
        small = self.image("small.png", (12, 12), "red")
        with self.assertRaises(HappyTripError):
            compose(self.asset, [{"path": small, "mask_path": str(self.mask)}], self.layout("masked_edit"), {})
        with self.assertRaises(HappyTripError):
            self.masked(protected_regions=[[0, 0, 1, 1]])

    def test_overlay_clips_protection(self):
        overlay = self.image("doodle.png", (20, 12), (255, 20, 20, 160), "RGBA")
        result = compose(self.asset, [{"path": overlay}], self.layout("overlay"), {"protected_regions": [[0, 0, .5, 1]]})
        with Image.open(result["path"]) as image, Image.open(self.source) as source:
            self.assertEqual(image.getpixel((2, 4))[:3], source.getpixel((2, 4)))
            self.assertNotEqual(image.getpixel((15, 4))[:3], source.getpixel((15, 4)))
        self.assertEqual(result["checks"][0]["status"], "pass")

    def poster(self, asset=None, **layout):
        return compose(asset or self.asset, [{"path": self.candidate, "box": [.1, .05, .8, .4]}], self.layout("B01", size=[100, 120], photo_box=[.1, .55, .8, .4], **layout), {})

    def test_b01_contain_reuses_original_and_records_transform(self):
        result = self.poster()
        record = result["provenance"][-1]
        self.assertEqual(record["source_kind"], "registered_original")
        self.assertEqual(record["input_sha256"], self.asset["input_sha256"])
        self.assertEqual(record["fit"], "contain")
        self.assertEqual(record["placed_box_px"][2:], [80, 48])

    def test_b01_rejects_regenerated_workcopy_even_with_updated_hash(self):
        forged = {**self.asset, "working_path": self.candidate, "working_sha256": sha256_file(self.candidate)}
        with self.assertRaisesRegex(HappyTripError, "normalized original"):
            self.poster(forged)

    def test_original_pixels_and_source_slot_overlap(self):
        result = self.poster(original_pixels=True)
        record = result["provenance"][-1]
        x, y, width, height = record["placed_box_px"]
        self.assertEqual((width, height), (20, 12))
        with Image.open(result["path"]) as image, Image.open(self.source) as original:
            self.assertEqual(image.crop((x, y, x + width, y + height)).convert("RGB").tobytes(), original.tobytes())
        with self.assertRaises(HappyTripError):
            compose(self.asset, [{"path": self.candidate, "box": [0, 0, 1, 1]}], self.layout("B01", output_path=str(self.root / "overlap.png")), {})

    def test_existing_source_symlink_never_overwritten(self):
        link = self.root / "alias.png"
        link.symlink_to(self.source)
        before = Path(self.source).read_bytes()
        with self.assertRaises(HappyTripError):
            compose(self.asset, [], self.layout("overlay", output_path=str(link)), {})
        self.assertEqual(Path(self.source).read_bytes(), before)

    def font(self):
        choices = [os.environ.get("HAPPYTRIP_TEST_FONT", ""), "/System/Library/Fonts/Supplemental/Arial Unicode.ttf", "/System/Library/Fonts/STHeiti Light.ttc", "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"]
        found = next((path for path in choices if path and Path(path).is_file()), None)
        if not found:
            self.skipTest("No CJK test font available; set HAPPYTRIP_TEST_FONT.")
        return found

    def route(self, **overrides):
        second = resolve_assets({"photos": [{"photo_id": "p02", "ref": self.candidate, "roles": ["scene"]}]}, workdir=self.root / "work")[0]
        layout = self.layout("B22", size=[600, 800], font_path=self.font(), font_size=22,
                             stops=[{"id": "s1", "name": "同名地点", "photo_ids": ["p01"]}, {"id": "s2", "name": "同名地点", "photo_ids": ["p02"]}])
        layout.update(overrides)
        return compose([self.asset, second], [], layout, {})

    def test_unknown_route_order_has_no_connections(self):
        result = self.route(ordered_stop_ids=["s2", "s1"], order_confirmed=False)
        self.assertEqual(result["route"]["edges"], [])
        self.assertEqual(result["route"]["ordered_stop_ids"], [])
        photos = [record for record in result["provenance"] if record["kind"] == "source_photo"]
        self.assertEqual([(p["stop_id"], p["photo_id"]) for p in photos], [("s1", "p01"), ("s2", "p02")])

    def test_confirmed_route_uses_only_approved_order_and_labels(self):
        result = self.route(ordered_stop_ids=["s2", "s1"], order_confirmed=True)
        self.assertEqual(result["route"]["edges"], [["s2", "s1"]])
        self.assertEqual(result["route"]["label"], "行程示意，非比例地图")

    def test_missing_font_and_text_overflow_fail(self):
        layer = {"kind": "text", "text": "Hello", "box": [0, 0, .1, .1], "font_size": 48}
        with self.assertRaisesRegex(HappyTripError, "font_path"):
            compose(self.asset, [layer], self.layout("overlay"), {})
        layer["font_path"] = self.font()
        with self.assertRaisesRegex(HappyTripError, "does not fit"):
            compose(self.asset, [layer], self.layout("overlay"), {})

    def test_export_metadata_and_status_remain_truthful(self):
        result = self.masked()
        job = {"job_id": "sample", "status": "candidate", "simulated": True, "image_assets": [{"path": result["path"]}], "provenance": [{"api_key": "hidden", "latitude": 12.3, "photo_id": "p01"}]}
        outputs = export_result(job, self.root / "delivery")
        manifest = json.loads((self.root / "delivery/manifest.json").read_text())
        self.assertEqual(manifest["status"], "candidate")
        self.assertTrue(manifest["simulated"])
        self.assertNotIn("hidden", json.dumps(manifest))
        self.assertNotIn("latitude", json.dumps(manifest))
        self.assertEqual(validate_image_file(outputs[0]["path"])["status"], "pass")
        self.assertEqual(validate_result(job)["status"], "not_run")
        with self.assertRaises(HappyTripError):
            export_result(job, self.root / "delivery")

    def test_missing_output_never_gets_export_link(self):
        with self.assertRaises(HappyTripError):
            export_result({"image_assets": [{"path": str(self.root / "missing.png")}]}, self.root / "delivery")
        self.assertFalse((self.root / "delivery").exists())

    def test_generic_canvas_supports_original_panels_and_generated_art(self):
        result = compose(None, [{"kind": "photo", "asset": self.asset, "box": [0, 0, .5, 1]},
                                {"kind": "image", "path": self.candidate, "box": [.5, 0, .5, 1], "source_photo_ids": ["p01"]}],
                         self.layout("canvas", size=[400, 300]), {})
        self.assertEqual(result["size"], [400, 300])
        self.assertEqual(result["provenance"][0]["source_kind"], "registered_original")
        self.assertEqual(result["provenance"][1]["source_photo_ids"], ["p01"])

    def test_suitcase_collage_requires_two_interiors_and_complete_mapping(self):
        layout = self.layout("collage", interior_regions=[[0, 0, .5, 1], [.5, 0, .5, 1]], selected_photo_ids=["p01", "p02"])
        layers = [{"path": self.candidate, "box": [.05, .1, .4, .8], "source_photo_ids": ["p01"]},
                  {"path": self.candidate, "box": [.55, .1, .4, .8], "source_photo_ids": ["p02"]}]
        result = compose(self.asset, layers, layout, {})
        self.assertEqual(result["validation"]["status"], "pass")
        layout["output_path"] = str(self.root / "failed.png")
        with self.assertRaisesRegex(HappyTripError, "must match"):
            compose(self.asset, layers[:1], layout, {})


if __name__ == "__main__":
    unittest.main()
