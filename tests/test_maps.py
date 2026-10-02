import copy
import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from happytrip_runtime.assets import sha256_file
from happytrip_runtime.maps import create_basemap, project_point, render_basemap, validate_geographic
from happytrip_runtime.runner import _check_request_privacy
from happytrip_runtime.types import HappyTripError


class GeographicMapTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.image = self.root / "map.png"
        Image.new("RGB", (512, 512), "#b9d9e4").save(self.image)
        self.spec = create_basemap(output=self.root / "map.json", image_path=self.image,
                                   bounds=[-1, -1, 1, 1], source="local test fixture",
                                   attribution="Fixture, not a real map")
        self.layout = {"basemap": self.spec, "stops": [
            {"id": "a", "coordinates": {"lon": -.5, "lat": .5, "source": "user", "confirmed": True}},
            {"id": "b", "coordinates": {"lon": .5, "lat": -.5, "source": "user", "confirmed": True}}],
            "order_confirmed": True, "ordered_stop_ids": ["a", "b"],
            "route_segments": [{"from": "a", "to": "b", "coordinates": [[-.5, .5], [0, .2], [.5, -.5]],
                                "source": "user", "source_reference": "test fixture", "confirmed": True, "kind": "planned_route"}]}

    def tearDown(self):
        self.temp.cleanup()

    def test_projection_and_letterbox_agree_without_stretching_map(self):
        image, record = render_basemap(self.spec, (800, 400))
        self.assertEqual(record["viewport_px"], [200, 0, 400, 400])
        self.assertEqual(project_point(0, 0, self.spec["bounds"], (400, 400)), (200, 200))
        x, y = project_point(-1, 1, self.spec["bounds"], (400, 400))
        self.assertAlmostEqual(x, 0)
        self.assertAlmostEqual(y, 0)
        self.assertEqual(image.getpixel((400, 200))[:3], (185, 217, 228))
        image.close()

    def test_tampered_map_and_incorrect_extent_do_not_render(self):
        bad = {**self.spec, "bounds": [-1, -1, 3, 1]}
        with self.assertRaisesRegex(HappyTripError, "aspect"):
            render_basemap(bad, (500, 500))
        self.image.write_bytes(self.image.read_bytes() + b"changed")
        with self.assertRaisesRegex(HappyTripError, "changed"):
            render_basemap(self.spec, (500, 500))

    def test_route_geometry_must_match_stops_and_order(self):
        valid = validate_geographic(self.layout)
        self.assertEqual(valid["route_segments"][0]["kind"], "planned_route")
        for change in ("reverse", "order", "bounds", "confirmation"):
            bad = copy.deepcopy(self.layout)
            if change == "reverse":
                bad["route_segments"][0]["coordinates"].reverse()
            elif change == "order":
                bad["order_confirmed"] = False
            elif change == "bounds":
                bad["stops"][0]["coordinates"]["lon"] = 2
            else:
                bad["route_segments"][0]["confirmed"] = False
            with self.subTest(change=change), self.assertRaises(HappyTripError):
                validate_geographic(bad)

    def test_missing_map_attribution_and_invalid_numeric_coordinates_fail(self):
        for field, value in (("attribution", ""), ("source", ""), ("projection", "wgs84")):
            bad = copy.deepcopy(self.layout)
            bad["basemap"][field] = value
            with self.subTest(field=field), self.assertRaises(HappyTripError):
                validate_geographic(bad)
        for lon in (True, float("nan"), float("inf"), -181):
            bad = copy.deepcopy(self.layout)
            bad["stops"][0]["coordinates"]["lon"] = lon
            with self.subTest(lon=lon), self.assertRaises(HappyTripError):
                validate_geographic(bad)

    def test_no_route_geometry_is_not_fabricated(self):
        layout = {**self.layout, "route_segments": [], "order_confirmed": False}
        self.assertEqual(validate_geographic(layout)["route_segments"], [])

    def test_geojson_render_preserves_holes_and_records_adjusted_extent(self):
        path = self.root / "source.geojson"
        path.write_text(json.dumps({"type": "FeatureCollection", "features": [
            {"type": "Feature", "properties": {"kind": "water"}, "geometry": {"type": "Polygon", "coordinates": [
                [[-.9, -.9], [.9, -.9], [.9, .9], [-.9, .9], [-.9, -.9]],
                [[-.2, -.2], [.2, -.2], [.2, .2], [-.2, .2], [-.2, -.2]]
            ]}}
        ]}))
        result = create_basemap(output=self.root / "vector.json", geojson_path=path,
                                bounds=[-1, -1, 1, 1], size=(512, 384), source="fixture", attribution="Test")
        self.assertLess(result["bounds"][0], -1)
        self.assertEqual(result["vector_source_sha256"], sha256_file(path))
        with Image.open(result["path"]) as im:
            self.assertEqual(im.getpixel((256, 192)), (238, 234, 224))
            self.assertEqual(im.getpixel((320, 192)), (185, 217, 228))
        raster, _ = render_basemap(result, (800, 600))
        raster.close()

    def test_registration_never_overwrites_sources_or_metadata(self):
        before = self.image.read_bytes()
        with self.assertRaises(HappyTripError):
            create_basemap(output=self.root / "map.json", image_path=self.image,
                           bounds=[-1, -1, 1, 1], source="test", attribution="test")
        self.assertEqual(self.image.read_bytes(), before)

    def test_geographic_privacy_retains_geometry_but_still_rejects_nested_secrets(self):
        request = {"mode_options": {**self.layout, "map_mode": "geographic"}}
        _check_request_privacy(request)
        request["mode_options"]["stops"][0]["coordinates"]["api_key"] = "hidden"
        with self.assertRaisesRegex(HappyTripError, "Credentials"):
            _check_request_privacy(request)
        with self.assertRaises(HappyTripError):
            _check_request_privacy({"mode_options": {"map_mode": "itinerary_schematic", "coordinates": [1, 2]}})


if __name__ == "__main__":
    unittest.main()
