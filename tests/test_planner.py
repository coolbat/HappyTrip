from copy import deepcopy
import unittest
from happytrip_runtime.catalog import load_catalog, get_mode
from happytrip_runtime.planner import make_plan

CAPS = {'image_generation': True, 'image_editing': True, 'masked_editing': True,
        'local_composition': True, 'exact_text_rendering': True, 'multiple_references': True,
        'max_reference_images': 8, 'geographic_rendering': True, 'transparent_assets': True}


def photo(index=1, roles=None):
    return {'photo_id': f'p{index}', 'roles': roles or ['scene'], 'working_path': f'/not-an-output/p{index}.png'}


class PlannerTests(unittest.TestCase):
    def setUp(self):
        self.catalog = load_catalog()

    def plan(self, mode, request=None, assets=None, caps=None):
        return make_plan(request or {}, assets if assets is not None else [photo()], get_mode(self.catalog, mode), CAPS if caps is None else caps)

    def test_b01_requires_original_composition_even_when_unknown(self):
        plan = self.plan('B01', caps={**CAPS, 'local_composition': 'unknown'})
        self.assertEqual(plan['status'], 'needs_capability')
        self.assertTrue(plan['contract']['strict_original'])
        self.assertIn('local_composition', plan['required_capabilities'])
        self.assertIn('magnet asset', plan['stages'][0]['instruction'])

    def test_no_image_generation_yields_prompt_only_not_success(self):
        plan = self.plan('A02', caps={**CAPS, 'image_generation': 'unknown'})
        self.assertEqual(plan['status'], 'prompt_only')
        self.assertEqual(plan['missing_capabilities'][0]['available'], 'unknown')

    def test_concert_locked_pose_conflicts(self):
        plan = self.plan('A09', {'edit_contract': {'preserve_pose': True}}, [photo(1, ['person'])])
        self.assertEqual(plan['status'], 'needs_input')
        self.assertIn('CONTRACT_CONFLICT', [e['code'] for e in plan['errors']])

    def test_local_candidate_without_strict_contract_is_possible(self):
        plan = self.plan('A01', {'targets': [{'photo_id': 'p1', 'description': '右侧路人'}]}, caps={'image_generation': True, 'image_editing': True})
        self.assertEqual(plan['status'], 'ready')
        self.assertFalse(plan['contract']['strict_original'])
        self.assertFalse(any(s['kind'] == 'compose' for s in plan['stages']))
        self.assertTrue(plan['warnings'])

    def test_strict_local_requires_composition(self):
        plan = self.plan('A06', {'targets': [{'photo_id': 'p1', 'description': '建筑'}], 'edit_contract': {'strict_original': True}}, caps={'image_generation': True})
        self.assertEqual(plan['status'], 'needs_capability')
        self.assertIn('local_composition', plan['required_capabilities'])

    def test_missing_targets_and_required_roles_stop_generation(self):
        for mode in ['A01', 'A03', 'A06', 'A10', 'A11', 'A04', 'A08', 'A09', 'B14']:
            self.assertEqual(self.plan(mode)['status'], 'needs_input', mode)

    def test_sticker_budget_includes_empty_suitcase(self):
        assets = [photo(i) for i in range(1, 12)]
        plan = self.plan('A07', assets=assets)
        self.assertEqual(plan['estimated_image_calls'], 12)
        self.assertEqual(plan['status'], 'needs_input')
        self.assertIn('BUDGET_EXCEEDED', [e['code'] for e in plan['errors']])
        approved = self.plan('A07', {'budget': {'max_image_calls': 12}}, assets=assets, caps={**CAPS, 'max_reference_images': 1, 'multiple_references': False})
        self.assertEqual(approved['status'], 'ready')
        self.assertEqual({m['photo_id'] for m in approved['asset_mapping']}, {a['photo_id'] for a in assets})
        self.assertTrue(all(len(s['photo_ids']) <= 1 for s in approved['stages'] if s['kind'] == 'generate'))

    def test_existing_suitcase_does_not_consume_generation_call(self):
        plan = self.plan('A07', assets=[photo(1), photo(2), photo(3, ['suitcase'])])
        self.assertEqual(plan['estimated_image_calls'], 2)
        self.assertEqual(plan['status'], 'ready')

    def test_sticker_alpha_capability_must_be_confirmed(self):
        plan = self.plan('A07', assets=[photo(1), photo(2)], caps={**CAPS, 'transparent_assets': 'unknown'})
        self.assertEqual(plan['status'], 'needs_capability')
        self.assertIn('transparent_assets', plan['required_capabilities'])

    def test_unknown_multiple_reference_limit_is_not_infinite(self):
        plan = self.plan('A08', assets=[photo(1, ['person']), photo(2)], caps={**CAPS, 'max_reference_images': None})
        self.assertEqual(plan['status'], 'needs_capability')
        self.assertIn('max_reference_images', plan['required_capabilities'])

    def test_request_and_assets_are_not_mutated(self):
        request = {'targets': [{'photo_id': 'p1', 'description': '指定人物'}], 'mode_options': {'makeup': False}}
        assets = [photo()]
        before = deepcopy((request, assets))
        self.plan('A03', request, assets)
        self.assertEqual((request, assets), before)

    def test_editing_capability_is_not_inferred_from_generation(self):
        request = {'targets': [{'photo_id': 'p1', 'description': '右侧路人'}]}
        plan = self.plan('A01', request, caps={**CAPS, 'image_editing': False})
        self.assertEqual(plan['status'], 'needs_capability')
        no_backend = self.plan('A01', request, caps={})
        self.assertEqual(no_backend['status'], 'prompt_only')

    def test_monetary_budget_is_never_silently_ignored(self):
        plan = self.plan('A02', {'budget': {'max_cost': 1.25, 'currency': 'USD'}})
        self.assertEqual(plan['status'], 'needs_input')
        self.assertIn('BUDGET_QUOTE_REQUIRED', [e['code'] for e in plan['errors']])

    def test_ordinary_protection_does_not_promise_pixel_identity(self):
        request = {'targets': [{'photo_id': 'p1', 'description': '右侧路人'}],
                   'protected': [{'photo_id': 'p1', 'description': '同行者'}]}
        plan = self.plan('A01', request)
        self.assertEqual(plan['status'], 'ready')
        self.assertFalse(plan['contract']['strict_original'])

    def test_malformed_story_is_clear_input_error(self):
        plan = self.plan('B16', {'mode_options': {'panels': 4}})
        self.assertEqual(plan['status'], 'needs_input')
        self.assertIn('STORY_INVALID', [e['code'] for e in plan['errors']])
