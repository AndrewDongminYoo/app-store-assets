"""Pre-hash snapshot capacity and repeated image validation regression tests."""

import hashlib
import json
import unittest
from unittest.mock import patch

from offline_support import fixture, module
from test_assets import png
from test_offline_boundaries import snapshot_fixture


class SnapshotAggregateBounds(unittest.TestCase):
    def setUp(self):
        self.root, profile = fixture(self)
        self.target = module("profiles").target_identity(
            profile["targets"]["production"]
        )
        self.record = json.loads((self.root / "metadata/listing.json").read_text())

    def test_snapshot_aggregate_rejects_before_hashing_any_payload(self):
        self.record["type"] = "metadata-snapshot"
        snapshot = snapshot_fixture(
            self.root / "downloads",
            self.record,
            {"one.txt": b"1234", "two.txt": b"5678"},
        )
        records = module("records")
        original = records._walk

        def only_reserve(*args, **kwargs):
            if not kwargs.get("reserve"):
                raise AssertionError("hash before aggregate reservation")
            return original(*args, **kwargs)

        with patch.object(records, "_walk", side_effect=only_reserve):
            with self.assertRaisesRegex(ValueError, "bound"):
                module("snapshots").validate_snapshot(snapshot, total_limit=7)
        self.assertEqual(
            module("snapshots").validate_snapshot(snapshot, total_limit=8)["record"],
            self.record,
        )

    def test_reserved_inventory_rejects_growing_file_before_hash(self):
        records = module("records")
        folder = self.root / "tree"
        folder.mkdir()
        source = folder / "public.txt"
        source.write_bytes(b"1234")
        original = records._walk

        def grow(*args, **kwargs):
            result = original(*args, **kwargs)
            if kwargs.get("reserve"):
                source.write_bytes(b"12345")
            return result

        with (
            patch.object(records, "_walk", side_effect=grow),
            patch.object(
                records,
                "digest_stream",
                side_effect=AssertionError("changed file hashed"),
            ),
        ):
            with self.assertRaisesRegex(ValueError, "changed"):
                records.tree_inventory(folder, total_limit=4)

    def test_repeated_snapshot_image_decodes_once_and_checks_every_annotation(self):
        image = png(1, 1)
        item = {
            "file": "images/public.png",
            "sha256": hashlib.sha256(image).hexdigest(),
            "width": 1,
        }
        self.record["images"] = {
            "en-US": {"APP_IPHONE_65": [dict(item) for _ in range(250)]}
        }
        snapshot = snapshot_fixture(
            self.root / "downloads", self.record, {item["file"]: image}
        )
        with patch.object(
            module("decoding"), "image_info", return_value=(1, 1, False)
        ) as decode:
            module("snapshots").validate_snapshot(snapshot)
            self.assertEqual(decode.call_count, 1)
        self.record["images"]["en-US"]["APP_IPHONE_65"][-1]["width"] = 2
        snapshot = snapshot_fixture(
            self.root / "downloads", self.record, {item["file"]: image}
        )
        with patch.object(
            module("decoding"), "image_info", return_value=(1, 1, False)
        ) as decode:
            with self.assertRaisesRegex(ValueError, "dimensions"):
                module("snapshots").validate_snapshot(snapshot)
            self.assertEqual(decode.call_count, 1)
