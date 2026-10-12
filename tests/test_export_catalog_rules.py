"""Export applies the catalog image rules that the matching import applies."""

import unittest

from local_image_support import image_snapshot
from offline_support import fixture, module
from test_assets import png


class ExportCatalogRules(unittest.TestCase):
    def setUp(self):
        self.root, profile = fixture(self)
        self.target = module("profiles").target_identity(
            profile["targets"]["production"]
        )

    def export(self, target, snapshot, destination, dry_run):
        return module("metadata_io").export_metadata(
            self.root, snapshot, target, destination, dry_run=dry_run
        )

    def assert_export_rejected(self, target, images, message):
        snapshot = image_snapshot(self.root, target, images)
        for dry in (True, False):
            with self.subTest(dry_run=dry):
                with self.assertRaisesRegex(ValueError, message):
                    self.export(target, snapshot, "editing", dry)
                self.assertFalse((self.root / "editing").exists())

    def test_unsupported_slot_dimensions_reject_export(self):
        self.assert_export_rejected(
            self.target, [png(100, 100)], "dimensions do not match slot"
        )

    def test_alpha_screenshot_rejects_export(self):
        self.assert_export_rejected(
            self.target,
            [png(1290, 2796, alpha=True, opacity=128)],
            "alpha channel is forbidden",
        )

    def test_one_invalid_image_among_valid_ones_rejects_export(self):
        self.assert_export_rejected(
            self.target,
            [png(1290, 2796), png(1290, 2796, alpha=True)],
            "alpha channel is forbidden",
        )

    def assert_uncovered_export_keeps_metadata_only(self, target, slot, images):
        # The catalog has no rule for these images, so only metadata-only
        # import can take the tree back; export must still produce it.
        snapshot = image_snapshot(self.root, target, images, slot=slot)
        for dry in (True, False):
            with self.subTest(dry_run=dry):
                destination = "editing-dry" if dry else "editing"
                self.export(target, snapshot, destination, dry)
                self.assertEqual((self.root / destination).exists(), not dry)
        editing = sorted((self.root / "editing" / "en-US" / "images").rglob("*.png"))
        self.assertEqual(len(editing), len(images))
        importer = module("metadata_io").import_metadata
        with self.assertRaises(ValueError):
            importer(self.root, "editing", target, "listing.json", "state")
        result = importer(
            self.root,
            "editing",
            target,
            "listing.json",
            "state",
            metadata_only=True,
            dry_run=True,
        )
        self.assertEqual(result["status"], "dry-run")

    def test_platform_without_catalog_slots_keeps_metadata_only_export(self):
        self.assert_uncovered_export_keeps_metadata_only(
            dict(self.target, platform="macos"), "APP_IPHONE_67", [png(1290, 2796)]
        )

    def test_slot_outside_catalog_keeps_metadata_only_export(self):
        self.assert_uncovered_export_keeps_metadata_only(
            self.target, "APP_IPHONE_55", [png(1242, 2208)]
        )

    def test_platform_without_catalog_slots_keeps_text_only_export(self):
        target = dict(self.target, platform="macos")
        snapshot = image_snapshot(self.root, target, [])
        self.export(target, snapshot, "editing", False)
        self.assertTrue((self.root / "editing").is_dir())

    def test_valid_export_round_trips_through_import(self):
        snapshot = image_snapshot(self.root, self.target, [png(1290, 2796)] * 2)
        for dry in (True, False):
            with self.subTest(dry_run=dry):
                destination = "editing-dry" if dry else "editing"
                self.export(self.target, snapshot, destination, dry)
                self.assertEqual((self.root / destination).exists(), not dry)
        result = module("metadata_io").import_metadata(
            self.root, "editing", self.target, "listing.json", "state"
        )
        self.assertTrue((self.root / result["listing"]).is_file())
        self.assertIsNotNone(result["assets"])


if __name__ == "__main__":
    unittest.main()
