"""Staged image copies trust their owned temporary ancestors; synthetic only."""

import hashlib
import tempfile
import unittest
from pathlib import Path

from local_image_support import image_snapshot
from offline_support import fixture, module
from test_assets import png


class StagedImageTrustedRoot(unittest.TestCase):
    def setUp(self):
        # The trusted input root stays outside the private-looking temp path.
        self.root, profile = fixture(self)
        self.target = module("profiles").target_identity(
            profile["targets"]["production"]
        )
        outer = tempfile.TemporaryDirectory(prefix="staged-trusted-root-")
        self.addCleanup(outer.cleanup)
        private = Path(outer.name).resolve() / ".codex"
        private.mkdir()
        previous = tempfile.tempdir
        tempfile.tempdir = str(private)
        # Cleanups run last-in first-out: restore before the outer rmtree.
        self.addCleanup(setattr, tempfile, "tempdir", previous)

    def test_catalog_validation_stages_under_private_looking_temp(self):
        (self.root / "public.png").write_bytes(png(1290, 2796))
        entry = {"file": "public.png", "locale": "en-US", "slot": "APP_IPHONE_67"}
        result = module("catalog").validate_images(self.root, [entry], "apple", "ios")
        self.assertEqual([item["file"] for item in result], ["public.png"])

    def test_snapshot_publication_stages_under_private_looking_temp(self):
        data = png(16, 16)
        image = {
            "file": "images/public.png",
            "sha256": hashlib.sha256(data).hexdigest(),
            "width": 16,
            "height": 16,
        }
        record = {
            "schema_version": 1,
            "type": "metadata-snapshot",
            "target": self.target,
            "fields": {},
            "images": {"en-US": {"APP_IPHONE_67": [image]}},
        }
        manifest = module("publisher").snapshot_manifest(record, {image["file"]: data})
        self.assertEqual(manifest["files"], {image["file"]: image["sha256"]})

    def test_export_stages_under_private_looking_temp(self):
        snapshot = image_snapshot(self.root, self.target, [png(1290, 2796)])
        for dry in (True, False):
            with self.subTest(dry_run=dry):
                destination = "editing-dry" if dry else "editing"
                result = module("metadata_io").export_metadata(
                    self.root, snapshot, self.target, destination, dry_run=dry
                )
                self.assertIsNotNone(result)
                self.assertEqual((self.root / destination).exists(), not dry)


if __name__ == "__main__":
    unittest.main()
