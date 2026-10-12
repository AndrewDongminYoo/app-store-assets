"""Export manifests hold at most IMAGE_ENTRY_LIMIT images."""

import unittest

from offline_support import fixture, module


class ExportImageLimit(unittest.TestCase):
    def test_export_manifest_rejects_images_above_the_entry_limit(self):
        root, profile = fixture(self)
        target = module("profiles").target_identity(profile["targets"]["production"])
        limit = module("contracts").IMAGE_ENTRY_LIMIT
        value = {
            "schema_version": 1,
            "type": "metadata-export",
            "target": target,
            "source_snapshot": "0" * 64,
            "format": "fastlane-repository-v1",
            "fields": [],
            "images": [
                {
                    "locale": "en-US",
                    "slot": "APP_IPHONE_67",
                    "file": f"en-US/images/iPhone67/{n:04}.png",
                }
                for n in range(limit + 1)
            ],
            "notes": [],
        }
        with self.assertRaisesRegex(ValueError, "entry limit"):
            module("metadata_io").validate_export(value, target)


if __name__ == "__main__":
    unittest.main()
