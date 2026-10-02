import tempfile
import unittest
from pathlib import Path
from happytrip_runtime.adapters.host import HostAdapter
from happytrip_runtime.adapters.mock import MockAdapter
from happytrip_runtime.adapters.base import normalize_capabilities


class AdapterTests(unittest.TestCase):
    def test_host_unknown_is_not_true_and_no_fake_file(self):
        host = HostAdapter()
        self.assertEqual(host.capabilities()["image_generation"], "unknown")
        self.assertEqual(host.execute({})["status"], "prompt_only")
        self.assertNotIn("path", host.execute({}))

    def test_mock_is_explicit_and_file_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = MockAdapter().execute({"output_dir": tmp, "stage_id": "s1"})
            self.assertTrue(result["simulated"])
            self.assertTrue(Path(result["path"]).is_file())

    def test_string_true_is_not_capability(self):
        with self.assertRaises(ValueError):
            normalize_capabilities({"image_generation": "true"})
