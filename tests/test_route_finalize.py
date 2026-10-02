"""Real local composition integration; fixture reviews do not certify art quality."""
import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from happytrip_runtime.adapters.host import HostAdapter
from happytrip_runtime.compositor import compose
from happytrip_runtime.runner import prepare_job, finalize_job, digest
from happytrip_runtime.types import HappyTripError


class RouteFinalizeTests(unittest.TestCase):
    def test_poster_export_requires_the_planned_facts_as_well_as_photos(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            font = next((p for p in ("/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
                         "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc") if Path(p).exists()), None)
            if not font:
                self.skipTest("No CJK fixture font")
            photos = []
            for i, color in enumerate(("#719e9b", "#a86452"), 1):
                path = root / f"p{i}.png"
                Image.new("RGB", (240, 160), color).save(path)
                photos.append({"photo_id": f"p{i}", "ref": str(path), "roles": ["scene"]})
            options = {"template": "travel_poster", "map_mode": "itinerary_schematic", "title": "测试行程",
                       "ordered_stop_ids": ["a", "b"], "order_confirmed": True,
                       "stops": [{"id": "a", "name": "测试甲", "photo_ids": ["p1"]},
                                 {"id": "b", "name": "测试乙", "photo_ids": ["p2"]}]}
            caps = {"vision": True, "local_composition": True, "exact_text_rendering": True}
            request = {"mode": "B22", "photos": photos, "mode_options": options, "capabilities": caps}
            job = root / "job"
            prepare_job(request, HostAdapter(caps), job)
            plan = json.loads((job / "plan.json").read_text())
            self.assertEqual(plan["status"], "ready", plan["errors"])
            assets = json.loads((job / "assets.json").read_text())
            for altered in (True, False):
                image = root / ("changed.png" if altered else "correct.png")
                layout = {**plan["route_layout"], "size": [600, 800], "font_path": font, "output_path": str(image)}
                if altered:
                    layout["title"] = "另一段行程"
                manifest = compose(assets, [], layout, plan["contract"])
                manifest_path = Path(str(image) + ".json")
                manifest_path.write_text(json.dumps(manifest))
                review = {"reviewer": "test fixture only", "image_sha256": digest(image), "visual_status": "pass",
                          "composition_manifest": str(manifest_path), "checks": [
                              {"name": name, "status": "pass", "reason": "Synthetic test fixture, interface check only"}
                              for name in ("mode_visual", "facts_and_text", "identity_and_subjects", "edit_scope")]}
                if altered:
                    with self.assertRaisesRegex(HappyTripError, "facts, map source or route"):
                        finalize_job(job, image, review)
                else:
                    result = finalize_job(job, image, review)
                    self.assertEqual(result["status"], "succeeded")
                    self.assertEqual(result["image_calls"], 0)
                    self.assertTrue(Path(result["image_assets"][0]["path"]).is_file())


if __name__ == "__main__":
    unittest.main()
