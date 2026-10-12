"""Every image validation path names a platform the frozen catalog supports."""

import hashlib
import unittest
from unittest.mock import patch

from offline_support import fixture, module
from test_assets import png
from test_offline_boundaries import snapshot_fixture


class ImagePlatformContract(unittest.TestCase):
    def setUp(self):
        self.root, self.profile = fixture(self)
        self.target = module("profiles").target_identity(
            self.profile["targets"]["production"]
        )

    def test_image_validation_requires_a_supported_platform_before_decode(self):
        (self.root / "public.png").write_bytes(png(1290, 2796))
        entry = {"file": "public.png", "locale": "en-US", "slot": "APP_IPHONE_67"}
        with patch.object(
            module("catalog"),
            "image_info",
            side_effect=AssertionError("unsupported platform image decoded"),
        ):
            for store, platform in (
                ("apple", "macos"),
                ("apple", "android"),
                ("google", "ios"),
            ):
                with self.subTest(store=store, platform=platform):
                    with self.assertRaisesRegex(ValueError, "platform"):
                        module("catalog").validate_images(
                            self.root, [entry], store, platform
                        )

    def test_macos_asset_snapshot_rejects_before_ios_slot_rules(self):
        data = png(1290, 2796)
        record = {
            "schema_version": 1,
            "type": "asset-manifest",
            "target": dict(self.target, platform="macos"),
            "assets": [
                {
                    "file": "public.png",
                    "locale": "en-US",
                    "slot": "APP_IPHONE_67",
                    "sha256": hashlib.sha256(data).hexdigest(),
                }
            ],
            "provenance": {"status": "unverified-import"},
        }
        folder = snapshot_fixture(self.root / "history", record, {"public.png": data})
        with patch.object(
            module("catalog"),
            "image_info",
            side_effect=AssertionError("macos snapshot image decoded"),
        ):
            with self.assertRaisesRegex(ValueError, "macos"):
                module("snapshots").validate_snapshot(folder)


if __name__ == "__main__":
    unittest.main()
