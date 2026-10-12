"""Export decodes every image before it publishes an editing tree."""

import unittest

from local_image_support import image_snapshot
from offline_support import fixture, module
from test_assets import png


class ExportImageDecoding(unittest.TestCase):
    def test_export_fully_decodes_unannotated_images(self):
        root, profile = fixture(self)
        target = module("profiles").target_identity(profile["targets"]["production"])
        data = png(1290, 2796)
        snapshot = image_snapshot(root, target, [data[: len(data) - 40]])
        for dry in (True, False):
            with self.subTest(dry_run=dry), self.assertRaises(ValueError):
                module("metadata_io").export_metadata(
                    root, snapshot, target, "editing", dry_run=dry
                )
        self.assertFalse((root / "editing").exists())


if __name__ == "__main__":
    unittest.main()
