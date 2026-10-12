"""Staging captures each entry within its image, artifact or text bound."""

import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from offline_support import fixture, module


class StagingPerFileLimits(unittest.TestCase):
    def setUp(self):
        self.root, _ = fixture(self)
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.output = Path(temp.name).resolve()

    def expected(self, names):
        return {
            name: hashlib.sha256((self.root / name).read_bytes()).hexdigest()
            for name in names
        }

    def test_images_and_text_use_their_own_capture_limits(self):
        staging = module("staging")
        (self.root / "notes.txt").write_text("Public notes")
        (self.root / "shot.png").write_bytes(b"\x89PNG\r\n\x1a\n")
        (self.root / "photo.JPEG").write_bytes(b"\xff\xd8\xff")
        limits = {}
        original = staging.capture_bytes

        def capture(path, *, limit):
            limits[Path(path).name] = limit
            return original(path, limit=limit)

        with patch.object(staging, "capture_bytes", capture):
            staging.stage_inventory(
                self.root,
                self.output / "staged",
                self.expected(["notes.txt", "shot.png", "photo.JPEG"]),
            )
        self.assertEqual(
            limits,
            {
                "notes.txt": module("records").TEXT_LIMIT,
                "shot.png": module("decoding").IMAGE_LIMIT,
                "photo.JPEG": module("decoding").IMAGE_LIMIT,
            },
        )

    def test_text_above_the_text_limit_is_not_staged(self):
        staging = module("staging")
        (self.root / "notes.txt").write_bytes(b"a" * (module("records").TEXT_LIMIT + 1))
        destination = self.output / "staged"
        with self.assertRaisesRegex(ValueError, "byte bound"):
            staging.stage_inventory(
                self.root, destination, self.expected(["notes.txt"])
            )
        self.assertFalse(destination.exists())

    def test_artifacts_are_bounded_only_by_the_remaining_total(self):
        staging = module("staging")
        text_limit = module("records").TEXT_LIMIT
        (self.root / "app.aab").write_bytes(b"a" * (text_limit + 1))
        (self.root / "app.apk").write_bytes(b"PK")
        (self.root / "app.ipa").write_bytes(b"PK")
        limits = {}
        original = staging.capture_bytes

        def capture(path, *, limit):
            limits[Path(path).name] = limit
            return original(path, limit=limit)

        destination = self.output / "staged"
        with patch.object(staging, "capture_bytes", capture):
            staging.stage_inventory(
                self.root,
                destination,
                self.expected(["app.aab", "app.apk", "app.ipa"]),
            )
        self.assertEqual(set(limits), {"app.aab", "app.apk", "app.ipa"})
        self.assertTrue(all(limit > text_limit for limit in limits.values()))
        self.assertEqual(
            (destination / "app.aab").read_bytes(),
            (self.root / "app.aab").read_bytes(),
        )


if __name__ == "__main__":
    unittest.main()
