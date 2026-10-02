from copy import deepcopy
import unittest
from happytrip_runtime.catalog import load_catalog, get_mode
from happytrip_runtime.planner import make_plan, plan_stickers, plan_comic, plan_route
from happytrip_runtime.types import HappyTripError
from tests.test_planner import CAPS, photo


class StoryMapTests(unittest.TestCase):
    def setUp(self):
        self.assets = [photo(1, ['person']), photo(2)]
        self.panels = [{'index': i, 'action': f'用户描述的动作{i}', 'photo_ids': ['p1'], 'dialogue': '', 'basis': 'user'} for i in range(1, 5)]
        self.stops = [{'id': 's1', 'name': '同名地点', 'photo_ids': ['p1']}, {'id': 's2', 'name': '同名地点', 'photo_ids': ['p2']}]

    def test_eleven_stickers_have_independent_source_mapping(self):
        assets = [photo(i) for i in range(1, 12)]
        stages = plan_stickers(assets)
        self.assertEqual(len(stages), 11)
        self.assertEqual([s['unit']['source_photo_ids'][0] for s in stages], [a['photo_id'] for a in assets])
        self.assertTrue(all(s['depends_on'] == [] for s in stages))
        self.assertTrue(all(s['unit']['repair_scope'] == 'stage_only' for s in stages))

    def test_three_four_valid_five_invalid(self):
        self.assertEqual(len(plan_comic(self.panels[:3], self.assets)), 3)
        self.assertEqual(len(plan_comic(self.panels, self.assets)), 4)
        with self.assertRaises(HappyTripError):
            plan_comic(self.panels + [self.panels[0]], self.assets)

    def test_comic_keeps_panel_record_and_character_reference(self):
        self.panels[1]['photo_ids'] = ['p2']
        stages = plan_comic(self.panels, self.assets)
        self.assertEqual(stages[1]['photo_ids'], ['p1', 'p2'])
        self.assertEqual(stages[1]['unit']['panel'], self.panels[1])
        self.assertEqual(stages[1]['depends_on'], [])
        self.assertEqual(stages[1]['unit']['repair_scope'], 'stage_only')

    def test_four_panel_budget_allows_initial_pass_warns_about_repairs(self):
        plan = make_plan({'mode_options': {'panels': self.panels, 'panel_count': 4}}, self.assets,
                         get_mode(load_catalog(), 'B16'), CAPS)
        self.assertEqual(plan['estimated_image_calls'], 4)
        self.assertEqual(plan['status'], 'ready')
        self.assertEqual(plan['estimated_max_with_repairs'], 8)
        self.assertTrue(any('repair' in warning for warning in plan['warnings']))

    def test_real_story_cannot_silently_contain_fiction(self):
        self.panels[0]['basis'] = 'fiction'
        plan = make_plan({'mode_options': {'panels': self.panels, 'panel_count': 4, 'story_basis': 'user_provided'}}, self.assets,
                         get_mode(load_catalog(), 'B16'), CAPS)
        self.assertEqual(plan['status'], 'needs_input')
        self.assertIn('STORY_BASIS_UNKNOWN', [e['code'] for e in plan['errors']])

    def test_unknown_route_does_not_connect_or_merge_names(self):
        layout = plan_route(self.stops)
        self.assertEqual(layout['edges'], [])
        self.assertEqual(len(layout['stops']), 2)
        self.assertIn('非比例', layout['label'])
        self.assertIsNone(layout['distance_km'])
        request = {'mode_options': {'stops': self.stops, 'ordered_stop_ids': ['s2', 's1'], 'order_confirmed': False}}
        plan = make_plan(request, self.assets, get_mode(load_catalog(), 'B22'), CAPS)
        self.assertEqual(plan['status'], 'needs_input')
        self.assertEqual(plan['route_layout']['edges'], [])

    def test_explicit_unordered_mode_is_ready_without_edges(self):
        request = {'mode_options': {'stops': self.stops, 'map_mode': 'unordered_places'}}
        plan = make_plan(request, self.assets, get_mode(load_catalog(), 'B22'), CAPS)
        self.assertEqual(plan['status'], 'ready')
        self.assertEqual(plan['estimated_image_calls'], 0)
        self.assertEqual(plan['route_layout']['edges'], [])

    def test_confirmed_order_preserves_photo_mapping(self):
        layout = plan_route(self.stops, ['s2', 's1'])
        self.assertEqual(layout['edges'], [{'from': 's2', 'to': 's1'}])
        self.assertEqual(layout['stops'], self.stops)
        with self.assertRaises(HappyTripError):
            plan_route(self.stops, ['s1', 's1'])

    def test_geographic_coordinates_need_provenance_and_named_axes(self):
        with self.assertRaises(HappyTripError):
            plan_route(self.stops, ['s1', 's2'], 'geographic')
        stops = deepcopy(self.stops)
        for stop in stops:
            stop['coordinates'] = {'lat': 30.2, 'lon': 120.1, 'source': 'user', 'confirmed': True}
        self.assertEqual(plan_route(stops, ['s1', 's2'], 'geographic')['map_mode'], 'geographic')
        stops[0]['coordinates']['lat'] = 120.1
        with self.assertRaises(HappyTripError) as caught:
            plan_route(stops, ['s1', 's2'], 'geographic')
        self.assertEqual(caught.exception.code, 'FACT_COORDINATES_INVALID')
        stops[0]['coordinates'] = {'value': [30.2, 120.1], 'source': 'user', 'confirmed': True}
        with self.assertRaises(HappyTripError):
            plan_route(stops, ['s1', 's2'], 'geographic')
