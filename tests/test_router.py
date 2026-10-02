import unittest
from happytrip_runtime.catalog import load_catalog
from happytrip_runtime.router import recommend, ALIASES
from happytrip_runtime.facts import normalize_facts
from happytrip_runtime.types import HappyTripError


class RouterTests(unittest.TestCase):
    def setUp(self):
        self.catalog = load_catalog()
        self.scene = [{'photo_id': 'p1', 'roles': ['scene']}]

    def test_explicit_mode_beats_roles_and_aliases(self):
        result = recommend({'mode': 'A05', 'user_goal': '美颜'}, [{'photo_id': 'p1', 'roles': ['person']}], self.catalog)
        self.assertEqual([r['mode'] for r in result], ['A05'])

    def test_every_mode_has_deterministic_alias(self):
        for mode, aliases in ALIASES.items():
            self.assertEqual(recommend({'user_goal': aliases[0]}, self.scene, self.catalog)[0]['mode'], mode)

    def test_only_relight_does_not_bundle_beauty(self):
        result = recommend({'user_goal': '只调光，不要美颜'}, self.scene, self.catalog)
        self.assertEqual([r['mode'] for r in result], ['A02'])

    def test_scene_and_unknown_order_recommendations(self):
        self.assertEqual([r['mode'] for r in recommend({}, self.scene, self.catalog)], ['A05', 'B01', 'B03'])
        result = recommend({}, self.scene + [{'photo_id': 'p2', 'roles': ['scene']}], self.catalog)
        self.assertEqual([r['mode'] for r in result], ['A07'])
        self.assertNotIn('probability', result[0])
        self.assertEqual(result[0]['selection'], 'suggestion')

    def test_intent_provenance_is_distinct_from_suggestion(self):
        self.assertEqual(recommend({'mode': 'A05'}, self.scene, self.catalog)[0]['selection'], 'explicit')
        self.assertEqual(recommend({'user_goal': '水彩明信片'}, self.scene, self.catalog)[0]['selection'], 'intent')

    def test_no_assets_no_false_visual_claim(self):
        self.assertEqual(recommend({}, [], self.catalog), [])
        self.assertEqual(recommend({'user_goal': '水彩明信片'}, [], self.catalog)[0]['mode'], 'A05')

    def test_unknown_id_not_guessed_and_auto_supported(self):
        with self.assertRaises(HappyTripError):
            recommend({'mode': 'A13'}, self.scene, self.catalog)
        self.assertEqual(recommend({'mode': 'auto'}, self.scene, self.catalog)[0]['mode'], 'A05')

    def test_facts_never_invent_date_or_promote_hypothesis(self):
        self.assertEqual(normalize_facts({})['confirmed'], [])
        facts = normalize_facts({'facts': [
            {'type': 'place', 'value': '杭州', 'source': 'user'},
            {'type': 'date', 'value': '2025-01-01', 'source': 'metadata'},
            {'value': '未经确认', 'source': 'verified_reference', 'confirmed': 'true'},
            {'value': '明确否定', 'source': 'user', 'confirmed': False}],
            'hypotheses': [{'value': '巴黎', 'source': 'user', 'confirmed': True}]})
        self.assertEqual([r['value'] for r in facts['confirmed']], ['杭州'])
        self.assertEqual(len(facts['hypotheses']), 4)
        self.assertTrue(all(r['confirmed'] is False for r in facts['hypotheses']))
