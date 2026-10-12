"""One record or validation call holds at most IMAGE_ENTRY_LIMIT image entries."""

import json
import unittest
from unittest.mock import patch

from offline_support import fixture, module


class ImageEntryLimit(unittest.TestCase):
    def setUp(self):
        self.root, profile = fixture(self)
        self.target = module("profiles").target_identity(
            profile["targets"]["production"]
        )
        self.limit = module("contracts").IMAGE_ENTRY_LIMIT

    def entries(self, count):
        return [
            {"file": f"i{n}.png", "locale": "en-US", "slot": "APP_IPHONE_67"}
            for n in range(count)
        ]

    def test_limit_matches_the_documented_value(self):
        self.assertEqual(self.limit, 2000)

    def test_validate_images_rejects_before_reading_any_entry(self):
        catalog = module("catalog")
        with patch.object(
            catalog, "file_digest", side_effect=AssertionError("entry read")
        ):
            with self.assertRaisesRegex(ValueError, "entry limit"):
                catalog.validate_images(
                    self.root, self.entries(self.limit + 1), "apple", "ios"
                )

    def test_listing_images_reject_above_limit_across_locales(self):
        record = json.loads((self.root / "metadata/listing.json").read_text())
        half = self.limit // 2 + 1
        record["images"] = {
            name: {"APP_IPHONE_67": [{"file": f"{name}/{n}.png"} for n in range(half)]}
            for name in ("en-US", "fr-FR")
        }
        with self.assertRaisesRegex(ValueError, "entry limit"):
            module("metadata").validate_public_metadata(record, self.target)
        record["images"]["fr-FR"]["APP_IPHONE_67"].pop()
        record["images"]["fr-FR"]["APP_IPHONE_67"].pop()
        module("metadata").validate_public_metadata(record, self.target)

    def test_asset_manifest_rejects_above_limit(self):
        record = {
            "schema_version": 1,
            "type": "asset-manifest",
            "target": self.target,
            "assets": [
                dict(item, sha256="0" * 64) for item in self.entries(self.limit + 1)
            ],
            "provenance": {"status": "unverified-import"},
        }
        with self.assertRaisesRegex(ValueError, "entry limit"):
            module("record_types").validate_assets(record, self.target)


if __name__ == "__main__":
    unittest.main()
