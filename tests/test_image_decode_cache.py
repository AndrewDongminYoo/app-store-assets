"""One image validation decodes each content hash once; synthetic inputs only."""

import unittest
from unittest.mock import patch

from offline_support import fixture, module
from test_assets import png


class ImageDecodeCache(unittest.TestCase):
    def setUp(self):
        self.root, _ = fixture(self)

    def entries(self, names, data):
        for name in names:
            (self.root / name).write_bytes(data)
        return [
            {"file": name, "locale": "en-US", "slot": "APP_IPHONE_67"} for name in names
        ]

    def test_identical_image_bytes_decode_once_per_validation(self):
        names = [f"public-{index}.png" for index in range(4)]
        entries = self.entries(names, png(1290, 2796))
        catalog = module("catalog")
        with patch.object(catalog, "image_info", wraps=catalog.image_info) as decode:
            result = catalog.validate_images(self.root, entries, "apple", "ios")
        self.assertEqual(decode.call_count, 1)
        self.assertEqual([item["file"] for item in result], names)

    def test_cached_decode_still_checks_each_entry_name(self):
        entries = self.entries(("public.png", "public.jpg"), png(1290, 2796))
        with self.assertRaisesRegex(ValueError, "extension"):
            module("catalog").validate_images(self.root, entries, "apple", "ios")


if __name__ == "__main__":
    unittest.main()
