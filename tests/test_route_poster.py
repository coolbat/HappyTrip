import copy
import math
import os
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

from happytrip_runtime.assets import resolve_assets, sha256_file
from happytrip_runtime.compositor import compose
from happytrip_runtime.types import HappyTripError


class TravelPosterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        candidates = [os.environ.get("HAPPYTRIP_TEST_FONT", ""), "/System/Library/Fonts/Supplemental/Arial Unicode.ttf", "/System/Library/Fonts/STHeiti Light.ttc", "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"]
        self.font = next((path for path in candidates if path and Path(path).is_file()), None)
        if not self.font:
            self.skipTest("A CJK test font is required.")

    def tearDown(self):
        self.temp.cleanup()

    def recipe(self, count=3, size=(1200, 1600), **changes):
        photos, stops = [], []
        colors = ["#c7dedf", "#e2bd90", "#94aaa0"]
        for index in range(count):
            path = self.root / f"photo-{index}.png"
            image = Image.new("RGB", (320, 240), colors[index % 3])
            draw = ImageDraw.Draw(image)
            draw.rectangle((0, 150, 320, 240), fill="#718277")
            draw.rectangle((70 + index % 20, 60, 240, 180), fill="#f4ead1")
            draw.polygon([(50, 65), (150, 10), (260, 65)], fill="#9f5545")
            image.save(path)
            pid = f"p{index + 1}"
            photos.append({"photo_id": pid, "ref": str(path), "roles": ["scene"]})
            stops.append({"id": f"s{index + 1}", "name": f"地点{index + 1}", "photo_ids": [pid]})
        assets = resolve_assets({"photos": photos}, workdir=self.root / "work")
        layout = {"kind": "B22", "size": list(size), "font_path": self.font,
                  "title": "城市漫游 · City Walk", "subtitle": "把路上的美好，留在这一页", "stops": stops,
                  "ordered_stop_ids": [stop["id"] for stop in stops], "order_confirmed": True,
                  "output_path": str(self.root / "poster.png")}
        layout.update(changes)
        return assets, layout

    def test_default_has_polaroids_and_exact_source_mappings(self):
        assets, layout = self.recipe()
        result = compose(assets, [], layout, {})
        self.assertEqual(result["route"]["template"], "travel_poster")
        photos = [record for record in result["provenance"] if record["kind"] == "source_photo"]
        self.assertEqual(len(photos), 3)
        self.assertEqual({record["photo_id"] for record in photos}, {"p1", "p2", "p3"})
        self.assertTrue(any(placement["rotation_degrees"] != 0 for record in photos for placement in record["placements"]))
        for record, asset in zip(photos, assets):
            self.assertEqual(record["working_sha256"], asset["working_sha256"])
            self.assertEqual({placement["occurrence"] for placement in record["placements"]}, {"header", "callout"})
        self.assertEqual(result["visual_review"], "not_run")

    def test_two_photos_and_fifteen_photos_small_canvas(self):
        for count in (2, 15):
            with self.subTest(count=count):
                assets, layout = self.recipe(count, (600, 800), output_path=str(self.root / f"poster-{count}.png"))
                result = compose(assets, [], layout, {})
                self.assertEqual(result["route"]["source_photo_count"], count)
                self.assertEqual(len([record for record in result["provenance"] if record["kind"] == "source_photo"]), count)

    def test_unconfirmed_collection_has_no_edges(self):
        assets, layout = self.recipe(order_confirmed=False)
        result = compose(assets, [], layout, {})
        self.assertEqual(result["route"]["edges"], [])
        self.assertEqual(result["route"]["ordered_stop_ids"], [])
        self.assertTrue(any("不代表旅行顺序" in record.get("text", "") for record in result["provenance"]))

    def test_original_pixel_contract_rejected(self):
        assets, layout = self.recipe()
        with self.assertRaisesRegex(HappyTripError, "scales and rotates"):
            compose(assets, [], layout, {"original_pixels": True})

    def test_confirmed_dates_footer_and_unconfirmed_fact_rejection(self):
        fact = {"value": "2026.10.01 — 10.03", "source": "user", "confirmed": True}
        assets, layout = self.recipe(date_range=fact, footer=[{"label": "天气", "value": "晴朗", "source": "user", "confirmed": True}])
        layout["stops"][0]["date"] = {**fact, "value": "2026.10.01"}
        result = compose(assets, [], layout, {})
        texts = [record.get("text", "") for record in result["provenance"]]
        self.assertIn(fact["value"], texts)
        self.assertTrue(any("天气" in text and "晴朗" in text for text in texts))
        layout["output_path"] = str(self.root / "bad-fact.png")
        layout["date_range"]["confirmed"] = False
        with self.assertRaises(HappyTripError):
            compose(assets, [], layout, {})

    def test_long_exact_text_fails_actionably_without_truncation(self):
        assets, layout = self.recipe(title="很长的准确标题" * 100)
        with self.assertRaisesRegex(HappyTripError, "not truncated"):
            compose(assets, [], layout, {})
        self.assertFalse(Path(layout["output_path"]).exists())

    def geographic(self, segments=False):
        assets, layout = self.recipe(2)
        bounds = [120, 30, 120.04, 30.04]
        ratio = math.radians(.04) / (math.asinh(math.tan(math.radians(30.04))) - math.asinh(math.tan(math.radians(30))))
        path = self.root / "map.png"
        Image.new("RGB", (round(800 * ratio), 800), "#e3eadc").save(path)
        layout["map_mode"] = "geographic"
        layout["basemap"] = {"path": str(path), "bounds": bounds, "projection": "web_mercator", "source": "synthetic_test", "attribution": "Synthetic map for renderer tests", "sha256": sha256_file(path)}
        points = [(120.005, 30.035), (120.035, 30.005)]
        for stop, (lon, lat) in zip(layout["stops"], points):
            stop["coordinates"] = {"lon": lon, "lat": lat, "source": "user", "confirmed": True}
        if segments:
            layout["route_segments"] = [{"from": "s1", "to": "s2", "coordinates": [list(points[0]), [120.015, 30.03], [120.03, 30.02], list(points[1])], "kind": "planned_route", "source": "user", "confirmed": True,
                                         "distance": {"value": "4.2 km", "source": "user", "confirmed": True}}]
        return assets, layout

    def test_geographic_preserves_projection_and_attribution(self):
        from happytrip_runtime.maps import project_point
        assets, layout = self.geographic()
        result = compose(assets, [], layout, {})
        map_record = next(record for record in result["provenance"] if record["kind"] == "basemap")
        x, y, width, height = map_record["viewport_px"]
        px, py = project_point(120.005, 30.035, layout["basemap"]["bounds"], (width, height))
        pin = result["route"]["pins"][0]
        self.assertAlmostEqual(pin["anchor_px"][0], x + px, places=1)
        self.assertAlmostEqual(pin["anchor_px"][1], y + py, places=1)
        self.assertEqual(result["route"]["label"], "站点连线，非道路路线")
        self.assertTrue(any(record.get("text") == layout["basemap"]["attribution"] for record in result["provenance"]))
        coordinate = next(record for record in result["provenance"] if record.get("field") == "callout_coordinates:s1:p1")
        self.assertEqual(coordinate["text"], "30.0350°N\n120.0050°E")
        self.assertEqual(coordinate["rendered_text"], coordinate["text"])
        self.assertEqual(result["route"]["map_layout"], "full_map")
        self.assertGreater(result["route"]["map_box_px"][2], result["size"][0] * .85)
        mx, my, mw, mh = result["route"]["map_box_px"]
        callouts = [placement for record in result["provenance"] if record["kind"] == "source_photo" for placement in record["placements"] if placement["occurrence"] == "callout"]
        self.assertEqual(len(callouts), 2)
        for card in callouts:
            self.assertTrue(card["on_map"])
            cx, cy = card["frame_origin_px"]
            cw, ch = card["frame_size_px"]
            self.assertTrue(mx <= cx < cx + cw <= mx + mw)
            self.assertTrue(my <= cy < cy + ch <= my + mh)
            for pin in result["route"]["pins"]:
                px, py = pin["anchor_px"]
                self.assertFalse(cx <= mx + px <= cx + cw and cy <= my + py <= cy + ch)

    def test_explicit_split_keeps_geographic_map(self):
        assets, layout = self.geographic()
        layout["map_layout"] = "split"
        result = compose(assets, [], layout, {})
        self.assertEqual(result["route"]["map_layout"], "split")
        self.assertLess(result["route"]["map_box_px"][2], result["size"][0] * .6)
        self.assertTrue(any(record["kind"] == "basemap" for record in result["provenance"]))

    def test_dense_geographic_layout_falls_back_without_omitting_photos(self):
        _, reference = self.geographic()
        assets, layout = self.recipe(5)
        layout.update(map_mode="geographic", basemap=reference["basemap"])
        for index, stop in enumerate(layout["stops"]):
            stop["coordinates"] = {"lon": 120.005 + index * .007, "lat": 30.035 - index * .007, "source": "user", "confirmed": True}
        result = compose(assets, [], layout, {})
        self.assertEqual(result["route"]["requested_map_layout"], "full_map")
        self.assertEqual(result["route"]["map_layout"], "split")
        self.assertTrue(result["route"]["fallback_reason"])
        self.assertEqual({record["photo_id"] for record in result["provenance"] if record["kind"] == "source_photo"}, {asset["photo_id"] for asset in assets})

    def test_full_map_requires_real_geographic_data(self):
        assets, layout = self.recipe(map_layout="full_map")
        with self.assertRaisesRegex(HappyTripError, "geographic mode"):
            compose(assets, [], layout, {})

    def test_supplied_geometry_and_distance_are_rendered(self):
        assets, layout = self.geographic(segments=True)
        result = compose(assets, [], layout, {})
        self.assertEqual(result["route"]["label"], "规划路线（非实录轨迹）")
        self.assertEqual(result["route"]["route_segments"][0]["kind"], "planned_route")
        self.assertTrue(any(record.get("text") == "4.2 km" for record in result["provenance"]))

    def test_classic_remains_explicitly_available(self):
        assets, layout = self.recipe(template="classic")
        result = compose(assets, [], layout, {})
        self.assertNotIn("template", result["route"])

    def test_malformed_ids_modes_and_discarded_geographic_data_fail_closed(self):
        for field in ("map_mode", "photo_id", "binding", "order", "basemap"):
            with self.subTest(field=field):
                assets, layout = self.recipe()
                if field == "map_mode":
                    layout["map_mode"] = []
                elif field == "photo_id":
                    assets[0]["photo_id"] = []
                elif field == "binding":
                    layout["stops"][0]["photo_ids"] = [[]]
                elif field == "order":
                    layout["ordered_stop_ids"] = [[], "s2", "s3"]
                else:
                    layout["basemap"] = {"path": "a map cannot be discarded"}
                with self.assertRaises(HappyTripError):
                    compose(assets, [], layout, {})


if __name__ == "__main__":
    unittest.main()
