"""Snapshot publication decodes each image content hash once."""

import hashlib
import unittest
from unittest.mock import patch

from offline_support import fixture, module
from test_assets import png


class PublisherFinalBatch(unittest.TestCase):
    def setUp(self):
        self.root, profile = fixture(self)
        self.target = module("profiles").target_identity(
            profile["targets"]["production"]
        )

    def record(self, images=None):
        return {
            "schema_version": 1,
            "type": "metadata-snapshot",
            "target": self.target,
            "fields": {},
            "images": {"en-US": {"APP_IPHONE_67": images}} if images else {},
        }

    def test_metadata_snapshot_decodes_each_content_hash_once(self):
        data = png(16, 16)
        sha = hashlib.sha256(data).hexdigest()
        images = [
            {"file": f"images/{n}.png", "sha256": sha, "width": 16, "height": 16}
            for n in range(3)
        ]
        decoding = module("decoding")
        with patch.object(decoding, "image_info", wraps=decoding.image_info) as decode:
            module("publisher").snapshot_manifest(
                self.record(images), {item["file"]: data for item in images}
            )
        self.assertEqual(decode.call_count, 1)

    def test_cached_decode_still_checks_each_image_name(self):
        data = png(16, 16)
        sha = hashlib.sha256(data).hexdigest()
        images = [
            {"file": name, "sha256": sha, "width": 16, "height": 16}
            for name in ("images/a.png", "images/b.jpg")
        ]
        with self.assertRaisesRegex(ValueError, "extension"):
            module("publisher").snapshot_manifest(
                self.record(images), {item["file"]: data for item in images}
            )


if __name__ == "__main__":
    unittest.main()
