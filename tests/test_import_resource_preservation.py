"""Import must reserve declared input bounds and preserve the editing tree."""

import json
import shutil
import unittest
from unittest.mock import patch

import test_local_metadata as roundtrip_support


class ImportResourcePreservation(unittest.TestCase):
    setup_store = roundtrip_support.MetadataRoundtripTests.setup_store
    export = roundtrip_support.MetadataRoundtripTests.export

    def test_reserved_history_ancestors_cannot_contain_editing_source(self):
        self.setup_store("google")
        original = self.export()
        for reserved in ("metadata", "assets"):
            for dry_run in (False, True):
                state = self.root / (reserved + str(dry_run))
                source = state / reserved / "editing"
                shutil.copytree(original, source)
                before = {
                    p.relative_to(source).as_posix(): p.read_bytes()
                    for p in source.rglob("*")
                    if p.is_file()
                }
                with (
                    self.subTest(reserved=reserved, dry_run=dry_run),
                    self.assertRaisesRegex(ValueError, "overlap"),
                ):
                    self.io.import_metadata(
                        self.root,
                        source,
                        self.target,
                        self.root / (reserved + str(dry_run) + ".json"),
                        state,
                        dry_run=dry_run,
                    )
                self.assertEqual(
                    {
                        p.relative_to(source).as_posix(): p.read_bytes()
                        for p in source.rglob("*")
                        if p.is_file()
                    },
                    before,
                )
                self.assertEqual(list((state / reserved).iterdir()), [source])

    def test_image_and_aggregate_bounds_precede_every_inventory_hash(self):
        import app_store_assets_local.budgets as budgets

        self.setup_store("google")
        source = self.export()
        manifest = json.loads((source / "store-assets-export.json").read_text())
        image_size = (source / manifest["images"][0]["file"]).stat().st_size
        total = sum(p.stat().st_size for p in source.rglob("*") if p.is_file())
        for metadata_only in (False, True):
            for bound, limit in (
                ("IMAGE_LIMIT", image_size - 1),
                ("FILE_LIMIT", total - 1),
            ):
                with (
                    self.subTest(metadata_only=metadata_only, bound=bound),
                    patch.object(self.io, bound, limit, create=True),
                    patch.object(
                        budgets,
                        "_hash_file",
                        side_effect=AssertionError("hash before all size bounds"),
                    ),
                ):
                    with self.assertRaisesRegex(ValueError, "bound"):
                        self.io.import_metadata(
                            self.root,
                            source,
                            self.target,
                            self.root / "blocked.json",
                            self.root / "history",
                            metadata_only=metadata_only,
                            dry_run=True,
                        )
                self.assertFalse((self.root / "blocked.json").exists())
                self.assertFalse((self.root / "history").exists())

    def test_exact_input_total_accepts_metadata_only_images(self):
        self.setup_store("google")
        source = self.export()
        total = sum(p.stat().st_size for p in source.rglob("*") if p.is_file())
        with patch.object(self.io, "FILE_LIMIT", total):
            result = self.io.import_metadata(
                self.root,
                source,
                self.target,
                self.root / "listing.json",
                self.root / "history",
                metadata_only=True,
                dry_run=True,
            )
        self.assertEqual(result["status"], "dry-run")

    def test_added_undeclared_file_is_rejected_without_hashing_it(self):
        import app_store_assets_local.budgets as budgets

        self.setup_store("google")
        source = self.export()
        (source / "unexpected.txt").write_bytes(b"public")
        with patch.object(
            budgets, "_hash_file", side_effect=AssertionError("undeclared file hashed")
        ):
            with self.assertRaisesRegex(ValueError, "inventory"):
                self.io.import_metadata(
                    self.root,
                    source,
                    self.target,
                    self.root / "listing.json",
                    self.root / "history",
                    metadata_only=True,
                    dry_run=True,
                )

    def test_text_size_is_rejected_before_inventory_hash(self):
        self.setup_store("google")
        source = self.export()
        text = source / "en-US/full_description.txt"
        text.write_bytes(b"x" * (self.io.TEXT_LIMIT + 1))
        import app_store_assets_local.budgets as budgets

        with patch.object(
            budgets, "_hash_file", side_effect=AssertionError("unbounded hash")
        ):
            with self.assertRaisesRegex(ValueError, "bound"):
                self.io.import_metadata(
                    self.root,
                    source,
                    self.target,
                    self.root / "blocked.json",
                    self.root / "history",
                    metadata_only=True,
                    dry_run=True,
                )

    def test_empty_staging_inventory_rejects_symlink_source_alias(self):
        from offline_support import module

        self.setup_store()
        real = self.root / "real"
        real.mkdir()
        alias = self.root / "alias"
        alias.symlink_to(real, target_is_directory=True)
        with self.assertRaises((ValueError, OSError)):
            module(self, "staging").stage_inventory(alias, real / "new", {})
        self.assertEqual(list(real.iterdir()), [])
