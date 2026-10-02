"""Travel-poster planning preserves sources and refuses unsupported facts."""
from copy import deepcopy
import hashlib
from pathlib import Path
import tempfile
import unittest

from PIL import Image

from happytrip_runtime.catalog import get_mode, load_catalog
from happytrip_runtime.planner import make_plan, validate_route_facts
from happytrip_runtime.types import HappyTripError
from tests.test_planner import CAPS, photo


def confirmed(value, source="user"):
    return {"value": value, "source": source, "confirmed": True}


class B22PlanningTests(unittest.TestCase):
    def setUp(self):
        self.mode = get_mode(load_catalog(), "B22")
        self.assets = [photo(1), photo(2)]
        self.stops = [
            {"id": "a", "name": "第一站", "photo_ids": ["p1"], "date": confirmed("2026.09.29")},
            {"id": "b", "name": "第二站", "photo_ids": ["p2"], "date": confirmed("2026.09.30")},
        ]
        self.options = {
            "template": "travel_poster", "stops": self.stops,
            "title": "我的旅行", "subtitle": "TRAVEL JOURNAL",
            "date_range": confirmed("2026.09.29—2026.09.30"),
            "footer": [{"label": "天气", **confirmed("晴", "verified_reference")}],
            "ordered_stop_ids": ["a", "b"], "order_confirmed": True,
            "size": [1200, 1800], "font_path": "/example/font.ttf", "font_size": 24,
        }

    def plan(self, options=None, assets=None):
        return make_plan({"mode_options": self.options if options is None else options},
                         self.assets if assets is None else assets, self.mode, CAPS)

    def geographic_options(self, directory):
        options = deepcopy(self.options)
        options["map_mode"] = "geographic"
        path = Path(directory) / "test-map.png"
        # This extent is about 0.793 wide per unit of Mercator height.
        Image.new("RGB", (80, 100), "#d9e7e4").save(path)
        options["basemap"] = {
            "path": str(path), "bounds": [-123, 37, -122, 38], "projection": "web_mercator",
            "source": "Synthetic test fixture", "attribution": "Test fixture; not a real map",
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
        for stop, lon, lat in zip(options["stops"], [-122.7, -122.2], [37.3, 37.7]):
            stop["coordinates"] = confirmed({"lat": lat, "lon": lon})
        options["route_segments"] = [{
            "from": "a", "to": "b", "coordinates": [[-122.7, 37.3], [-122.2, 37.7]],
            "kind": "planned_route", "source": "user", "confirmed": True,
            "distance": confirmed("2.7 km"),
        }]
        return options

    def test_poster_plan_is_ready_with_complete_source_records(self):
        before = deepcopy(self.options)
        plan = self.plan()
        self.assertEqual(plan["status"], "ready")
        self.assertEqual(plan["estimated_image_calls"], 0)
        layout = plan["route_layout"]
        for field in ("template", "title", "subtitle", "date_range", "footer", "size", "font_path"):
            self.assertEqual(layout[field], self.options[field])
        self.assertTrue(layout["order_confirmed"])
        self.assertEqual(layout["stops"], self.stops)
        self.assertFalse(layout["is_road_route"])
        self.assertEqual(self.options, before)

    def test_metadata_cannot_become_a_printed_fact_without_confirmation(self):
        for field in ("date_range", "stop_date", "footer"):
            with self.subTest(field=field):
                options = deepcopy(self.options)
                record = (options["stops"][0]["date"] if field == "stop_date" else
                          options["footer"][0] if field == "footer" else options[field])
                record["source"] = "metadata"
                record["confirmed"] = False
                plan = self.plan(options)
                self.assertEqual(plan["status"], "needs_input")
                self.assertIn("FACT_UNCONFIRMED", [e["code"] for e in plan["errors"]])

    def test_user_fact_also_requires_explicit_confirmation(self):
        options = deepcopy(self.options)
        options["date_range"].pop("confirmed")
        self.assertEqual(self.plan(options)["status"], "needs_input")

    def test_direct_layout_fact_validation_refuses_untrusted_segment_distance(self):
        with self.assertRaises(HappyTripError) as caught:
            validate_route_facts({"route_segments": [{"source": "user", "confirmed": True,
                                                       "distance": confirmed("9.3 km", "model_guess")}]})
        self.assertEqual(caught.exception.code, "FACT_UNCONFIRMED")

    def test_model_guessed_route_cannot_become_a_recorded_track(self):
        with tempfile.TemporaryDirectory() as directory:
            options = self.geographic_options(directory)
            options["route_segments"][0].update(source="model_guess", kind="recorded_track")
            plan = self.plan(options)
        self.assertEqual(plan["status"], "needs_input")
        self.assertIn("FACT_UNCONFIRMED", [e["code"] for e in plan["errors"]])

    def test_malformed_poster_mode_produces_input_error(self):
        for field in ("map_mode", "template"):
            with self.subTest(field=field):
                options = deepcopy(self.options)
                options[field] = []
                self.assertEqual(self.plan(options)["status"], "needs_input")

    def test_unordered_collection_is_ready_and_carries_no_route_edges(self):
        options = deepcopy(self.options)
        options["map_mode"] = "unordered_places"
        options["order_confirmed"] = False
        plan = self.plan(options)
        self.assertEqual(plan["status"], "ready")
        self.assertEqual(plan["route_layout"]["ordered_stop_ids"], [])
        self.assertEqual(plan["route_layout"]["edges"], [])

    def test_unconfirmed_order_never_connects_a_poster(self):
        options = deepcopy(self.options)
        options["order_confirmed"] = False
        plan = self.plan(options)
        self.assertEqual(plan["status"], "needs_input")
        self.assertFalse(plan["route_layout"]["order_confirmed"])
        self.assertEqual(plan["route_layout"]["edges"], [])

    def test_unmapped_selected_photo_is_not_silently_dropped(self):
        plan = self.plan(assets=[*self.assets, photo(3)])
        self.assertEqual(plan["status"], "needs_input")
        self.assertIn("ASSET_MAPPING_MISSING", [e["code"] for e in plan["errors"]])

    def test_geographic_plan_preserves_basemap_and_confirmed_route_without_extra_permission_flag(self):
        with tempfile.TemporaryDirectory() as directory:
            options = self.geographic_options(directory)
            plan = self.plan(options)
        self.assertEqual(plan["status"], "ready", plan["errors"])
        self.assertEqual(plan["route_layout"]["basemap"]["sha256"], options["basemap"]["sha256"])
        self.assertEqual(plan["route_layout"]["route_segments"], options["route_segments"])
        self.assertFalse(plan["route_layout"]["is_road_route"])

    def test_geographic_plan_requires_the_actual_basemap_not_coordinates_alone(self):
        with tempfile.TemporaryDirectory() as directory:
            options = self.geographic_options(directory)
            options.pop("basemap")
            plan = self.plan(options)
        self.assertEqual(plan["status"], "needs_input")

    def test_unconfirmed_geographic_order_does_not_invent_edges(self):
        with tempfile.TemporaryDirectory() as directory:
            options = self.geographic_options(directory)
            options["order_confirmed"] = False
            options.pop("route_segments")
            plan = self.plan(options)
        self.assertEqual(plan["status"], "needs_input")
        self.assertEqual(plan["route_layout"]["edges"], [])
        self.assertIn("FACT_ORDER_UNKNOWN", [e["code"] for e in plan["errors"]])


if __name__ == "__main__":
    unittest.main()
