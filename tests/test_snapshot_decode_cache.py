"""Metadata snapshot validation decodes each image content hash once."""

import hashlib
import unittest
from unittest.mock import patch

from offline_support import fixture, module
from test_assets import png
from test_offline_boundaries import snapshot_fixture


class SnapshotDecodeCache(unittest.TestCase):
    def setUp(self):
        self.root, profile = fixture(self)
        self.target = module("profiles").target_identity(
            profile["targets"]["production"]
        )

    def test_metadata_snapshot_decodes_each_content_hash_once(self):
        data = png(16, 16)
        sha = hashlib.sha256(data).hexdigest()
        images = [
            {"file": f"images/{n}.png", "sha256": sha, "width": 16, "height": 16}
            for n in range(3)
        ]
        record = {
            "schema_version": 1,
            "type": "metadata-snapshot",
            "target": self.target,
            "fields": {},
            "images": {"en-US": {"APP_IPHONE_67": images}},
        }
        files = {item["file"]: data for item in images}
        folder = snapshot_fixture(self.root / "downloads", record, files)
        decoding = module("decoding")
        with patch.object(decoding, "image_info", wraps=decoding.image_info) as decode:
            module("snapshots").validate_snapshot(folder)
        self.assertEqual(decode.call_count, 1)


if __name__ == "__main__":
    unittest.main()
