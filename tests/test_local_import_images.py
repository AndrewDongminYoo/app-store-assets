"""Import image validation uses the target platform and bounded decoding."""

import unittest
from unittest.mock import patch

from local_image_support import image_snapshot
from offline_support import fixture, module
from test_assets import png


class LocalImportImages(unittest.TestCase):
    def setUp(self):
        self.root, profile = fixture(self)
        self.target = module("profiles").target_identity(
            profile["targets"]["production"]
        )

    def exported(self, target, images):
        snapshot = image_snapshot(self.root, target, images)
        return module("metadata_io").export_metadata(
            self.root, snapshot, target, "editing"
        )

    def import_dry_run(self, source, target, metadata_only=False):
        return module("metadata_io").import_metadata(
            self.root,
            source,
            target,
            "listing.json",
            "state",
            metadata_only=metadata_only,
            dry_run=True,
        )

    def test_macos_import_rejects_images_but_keeps_metadata_only(self):
        target = dict(self.target, platform="macos")
        source = self.exported(target, [png(1290, 2796)])
        with patch.object(
            module("catalog"),
            "image_info",
            side_effect=AssertionError("macos import image decoded"),
        ):
            with self.assertRaisesRegex(ValueError, "macos"):
                self.import_dry_run(source, target)
        result = self.import_dry_run(source, target, metadata_only=True)
        self.assertEqual(result["status"], "dry-run")

    def test_import_decodes_each_content_hash_independent_of_path_count(self):
        source = self.exported(self.target, [png(1290, 2796)] * 4)
        catalog = module("catalog")
        with patch.object(catalog, "image_info", wraps=catalog.image_info) as decode:
            self.import_dry_run(source, self.target)
        # One decode for validation and one for snapshot prediction.
        self.assertLessEqual(decode.call_count, 2)


if __name__ == "__main__":
    unittest.main()
