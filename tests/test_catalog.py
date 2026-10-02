import json
from pathlib import Path
import tempfile
import unittest
from happytrip_runtime.catalog import load_catalog, get_mode, MODE_IDS, VARIABLES
from happytrip_runtime.types import HappyTripError


class CatalogTests(unittest.TestCase):
    def test_fixed_modes_priorities_and_selected_card(self):
        catalog = load_catalog()
        self.assertEqual({m['id'] for m in catalog['modes']}, set(MODE_IDS))
        self.assertEqual(sum(m['validation_priority'] == 'P0' for m in catalog['modes']), 8)
        self.assertEqual(set(catalog['template_variables']), VARIABLES)
        for mode_id in MODE_IDS:
            self.assertTrue(Path(get_mode(catalog, mode_id)['template_path']).is_file())

    def test_unknown_mode_is_not_guessed(self):
        with self.assertRaisesRegex(HappyTripError, 'Unknown V1 mode'):
            get_mode(load_catalog(), 'B02')

    def test_duplicate_catalog_is_rejected(self):
        catalog = load_catalog()
        catalog['modes'][1] = catalog['modes'][0]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'catalog.json'
            path.write_text(json.dumps(catalog))
            with self.assertRaises(HappyTripError) as caught:
                load_catalog(path)
            self.assertEqual(caught.exception.code, 'CATALOG_INVALID')

    def test_get_mode_returns_independent_copy(self):
        catalog = load_catalog()
        mode = get_mode(catalog, 'a01')
        mode['options']['target_required'] = False
        self.assertTrue(get_mode(catalog, 'A01')['options']['target_required'])
