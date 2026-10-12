"""Asset manifests cannot claim rendered provenance without capture evidence."""

import unittest

from offline_support import fixture, module


class AssetProvenance(unittest.TestCase):
    def record(self, status):
        root, profile = fixture(self)
        target = module("profiles").target_identity(profile["targets"]["production"])
        return target, {
            "schema_version": 1,
            "type": "asset-manifest",
            "target": target,
            "assets": [
                {
                    "file": "public.png",
                    "locale": "en-US",
                    "slot": "APP_IPHONE_67",
                    "sha256": "0" * 64,
                }
            ],
            "provenance": {"status": status},
        }

    def test_widget_rendered_label_alone_is_rejected(self):
        target, record = self.record("widget-rendered")
        with self.assertRaisesRegex(ValueError, "provenance"):
            module("record_types").validate_assets(record, target)

    def test_unverified_import_remains_accepted(self):
        target, record = self.record("unverified-import")
        module("record_types").validate_assets(record, target)


if __name__ == "__main__":
    unittest.main()
