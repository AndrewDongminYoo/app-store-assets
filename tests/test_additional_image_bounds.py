"""Reject oversized image captures before retaining/staging their contents."""

import hashlib
import unittest
from unittest.mock import patch

import test_offline_image_binding as images

import app_store_assets_local.publisher as publisher


class AdditionalImageBounds(unittest.TestCase):
    def test_path_image_is_bounded_before_capture(self):
        root, folder, record, _ = images.fixture(self)
        path = folder / "public.png"
        with path.open("ab") as stream:
            stream.truncate(64 * 1024 * 1024 + 1)
        original = publisher.capture_bytes

        def guarded_capture(path, *, limit):
            self.assertLessEqual(
                limit, 64 * 1024 * 1024, "oversized capture would retain image bytes"
            )
            return original(path, limit=limit)

        output = root / "new-history"
        with patch.object(publisher, "capture_bytes", side_effect=guarded_capture):
            with self.assertRaisesRegex(ValueError, "bound|limit"):
                publisher.publish_snapshot(output, record, {"public.png": path})
        self.assertFalse(output.exists())

    def test_supplied_oversized_image_bytes_reject_before_temporary_staging(self):
        root, _, record, _ = images.fixture(self)
        data = b"x" * (64 * 1024 * 1024 + 1)
        record["images"]["en-US"]["phoneScreenshots"][0]["sha256"] = hashlib.sha256(
            data
        ).hexdigest()
        with patch.object(
            publisher.tempfile,
            "TemporaryDirectory",
            side_effect=AssertionError("oversized image reached staging"),
        ):
            with self.assertRaisesRegex(ValueError, "bound|limit"):
                publisher.snapshot_manifest(record, {"public.png": data})
        self.assertFalse((root / "history").exists())
