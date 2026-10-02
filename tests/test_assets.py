import tempfile
import unittest
from pathlib import Path

from PIL import Image
from happytrip_runtime.assets import resolve_assets, sha256_file
from happytrip_runtime.types import HappyTripError


class AssetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / "source.png"
        Image.new("RGB", (12, 8), "red").save(self.source)

    def tearDown(self):
        self.temp.cleanup()

    def request(self, **photo):
        return {"photos": [{"photo_id": "p01", "ref": str(self.source), "roles": ["base"], **photo}]}

    def test_source_readonly_and_hashes(self):
        before = self.source.read_bytes()
        asset = resolve_assets(self.request(), workdir=self.root / "work")[0]
        self.assertEqual(self.source.read_bytes(), before)
        self.assertEqual(asset["input_sha256"], sha256_file(self.source))
        self.assertEqual(asset["working_sha256"], sha256_file(asset["working_path"]))
        self.assertNotEqual(str(self.source), asset["working_path"])

    def test_missing_empty_document_and_example_refs(self):
        empty = self.root / "empty.png"
        empty.touch()
        document = self.root / "article.pdf"
        document.write_text("%PDF-1.7 article, not a selected photo")
        for ref in (None, "example-photo-01", str(empty), str(document)):
            with self.subTest(ref=ref), self.assertRaises(HappyTripError):
                resolve_assets(self.request(ref=ref), workdir=self.root / "work")

    def test_orientation_and_metadata_removed(self):
        source = self.root / "rotated.jpg"
        exif = Image.Exif()
        exif[274] = 6
        exif[270] = "private description"
        Image.new("RGB", (12, 8), "blue").save(source, exif=exif)
        asset = resolve_assets(self.request(ref=str(source)), workdir=self.root / "work")[0]
        self.assertEqual((asset["width"], asset["height"]), (8, 12))
        with Image.open(asset["working_path"]) as copy:
            self.assertFalse(copy.getexif())
            self.assertFalse(copy.info)

    def test_masks_follow_normalized_dimensions(self):
        mask = self.root / "mask.png"
        Image.new("L", (8, 12), 0).save(mask)
        with self.assertRaisesRegex(HappyTripError, "dimensions"):
            resolve_assets(self.request(mask_ref=str(mask)), workdir=self.root / "work")

    def test_bad_roles_regions_and_unknown_photo(self):
        with self.assertRaises(HappyTripError):
            resolve_assets(self.request(roles=["document"]), workdir=self.root / "work")
        for region in ({"photo_id": "missing", "box": [0, 0, 1, 1]}, {"photo_id": "p01", "box": [0.9, 0, 0.3, 1]}):
            request = self.request()
            request["targets"] = [region]
            with self.assertRaises(HappyTripError):
                resolve_assets(request, workdir=self.root / "work")

    def test_attachment_resolver(self):
        assets = resolve_assets(self.request(ref="attachment:real"), resolver=lambda ref: self.source, workdir=self.root / "work")
        self.assertEqual(assets[0]["ref"], str(self.source.resolve()))


if __name__ == "__main__":
    unittest.main()
