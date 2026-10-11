"""Approved publication/export/decode and output diagnostic regressions."""

import copy
import hashlib
import unittest
from unittest.mock import patch

from offline_support import fixture, module
from test_assets import png
from test_offline_boundaries import snapshot_fixture


class ApprovedLocalCompletion(unittest.TestCase):
    def setUp(self):
        self.root, profile = fixture(self)
        self.target = module("profiles").target_identity(
            profile["targets"]["production"]
        )
        self.record = {
            "schema_version": 1,
            "type": "metadata-snapshot",
            "target": self.target,
            "fields": {},
            "images": {},
        }

    def test_file_root_rejects_import_dry_run_and_direct_capture(self):
        snapshot = snapshot_fixture(self.root / "downloads", self.record)
        io = module("metadata_io")
        source = io.export_metadata(self.root, snapshot, self.target, "editing")
        state = self.root / "state-file"
        state.write_bytes(b"preserve")
        for dry in (False, True):
            with (
                self.subTest(dry_run=dry),
                self.assertRaisesRegex(ValueError, "directory"),
            ):
                io.import_metadata(
                    self.root,
                    source,
                    self.target,
                    "new.json",
                    state,
                    metadata_only=True,
                    dry_run=dry,
                )
        original = self.root / "public.txt"
        original.write_text("public source")
        with patch.object(
            module("publisher"),
            "capture_bytes",
            side_effect=AssertionError("invalid root captured source"),
        ):
            with self.assertRaisesRegex(ValueError, "directory"):
                module("publisher").publish_snapshot(
                    state, self.record, {"public.txt": original}
                )
        self.assertEqual(state.read_bytes(), b"preserve")
        self.assertFalse((self.root / "new.json").exists())

    def test_export_total_precedes_payload_hash_in_real_and_dry_run(self):
        snapshot = snapshot_fixture(
            self.root / "downloads",
            self.record,
            {"one.txt": b"1234", "two.txt": b"5678"},
        )
        records = module("records")
        original = records._walk

        def only_reserve(*args, **kwargs):
            if not kwargs.get("reserve"):
                raise AssertionError("unreserved payload hashed")
            return original(*args, **kwargs)

        for dry in (False, True):
            with (
                self.subTest(dry_run=dry),
                patch.object(module("metadata_io"), "FILE_LIMIT", 7),
                patch.object(records, "_walk", side_effect=only_reserve),
            ):
                with self.assertRaisesRegex(ValueError, "bound"):
                    module("metadata_io").export_metadata(
                        self.root, snapshot, self.target, "blocked", dry_run=dry
                    )
        self.assertFalse((self.root / "blocked").exists())

    def test_final_export_verification_also_reserves_before_hash(self):
        snapshot = snapshot_fixture(self.root / "downloads", self.record)
        io = module("metadata_io")
        original = io.validate_snapshot
        limits = []

        def check(*args, **kwargs):
            limits.append(kwargs.get("total_limit"))
            return original(*args, **kwargs)

        with patch.object(io, "validate_snapshot", side_effect=check):
            io.export_metadata(
                self.root, snapshot, self.target, "editing", dry_run=True
            )
        self.assertEqual(limits, [io.FILE_LIMIT, io.FILE_LIMIT])

    def test_duplicate_image_decode_once_but_every_annotation_checked(self):
        image = png(1, 1)
        item = {
            "file": "images/public.png",
            "sha256": hashlib.sha256(image).hexdigest(),
            "width": 1,
            "height": 1,
        }
        self.record["images"] = {
            "en-US": {"APP_IPHONE_65": [dict(item) for _ in range(250)]}
        }
        before = copy.deepcopy(self.record)
        with patch.object(
            module("decoding"), "image_info", return_value=(1, 1, False)
        ) as decode:
            manifest = module("publisher").snapshot_manifest(
                self.record, {item["file"]: image}
            )
            self.assertEqual(decode.call_count, 1)
        self.assertEqual(manifest["record"], before)
        self.record["images"]["en-US"]["APP_IPHONE_65"][-1]["width"] = 2
        with patch.object(
            module("decoding"), "image_info", return_value=(1, 1, False)
        ) as decode:
            with self.assertRaisesRegex(ValueError, "dimensions"):
                module("publisher").snapshot_manifest(
                    self.record, {item["file"]: image}
                )
            self.assertEqual(decode.call_count, 1)

    def test_manifest_size_rejects_before_decode(self):
        image = png(1, 1)
        item = {
            "file": "images/public.png",
            "sha256": hashlib.sha256(image).hexdigest(),
        }
        self.record["images"] = {"en-US": {"APP_IPHONE_65": [item]}}
        with (
            patch.object(module("publisher"), "TEXT_LIMIT", 8),
            patch.object(
                module("decoding"),
                "image_info",
                side_effect=AssertionError("oversized manifest decoded image"),
            ),
        ):
            with self.assertRaisesRegex(ValueError, "bound"):
                module("publisher").snapshot_manifest(
                    self.record, {item["file"]: image}
                )

    def test_export_capture_uses_same_image_limit_as_reservation(self):
        image = png(1, 1)
        item = {
            "file": "images/public.png",
            "sha256": hashlib.sha256(image).hexdigest(),
        }
        self.record["images"] = {"en-US": {"APP_IPHONE_65": [item]}}
        snapshot = snapshot_fixture(
            self.root / "downloads", self.record, {item["file"]: image}
        )
        with patch.object(module("metadata_io"), "IMAGE_LIMIT", len(image) - 1):
            with self.assertRaisesRegex(ValueError, "bound"):
                module("metadata_io").export_metadata(
                    self.root, snapshot, self.target, "blocked", dry_run=True
                )
