"""validate_images captures within the image bound before any full-file hash."""

import unittest
from pathlib import Path
from unittest.mock import patch

from offline_support import fixture, module
from test_assets import png


class ImageCaptureOrder(unittest.TestCase):
    def setUp(self):
        self.root, profile = fixture(self)
        self.target = module("profiles").target_identity(
            profile["targets"]["production"]
        )

    def test_image_capture_is_bounded_before_any_full_file_hash(self):
        (self.root / "public.png").write_bytes(png(1290, 2796))
        entry = {"file": "public.png", "locale": "en-US", "slot": "APP_IPHONE_67"}
        catalog = module("catalog")
        order = []

        def record(name, original):
            def call(path, *args, **kwargs):
                if Path(path).name == "public.png":
                    order.append(name)
                return original(path, *args, **kwargs)

            return call

        with (
            patch.object(catalog, "file_digest", record("digest", catalog.file_digest)),
            patch.object(
                catalog, "capture_bytes", record("capture", catalog.capture_bytes)
            ),
        ):
            catalog.validate_images(self.root, [entry], "apple", "ios")
        self.assertEqual(order[0], "capture")


if __name__ == "__main__":
    unittest.main()
