"""Actual history roots reject before input hashing, in real and dry imports."""

import unittest
from unittest.mock import patch

import test_local_metadata as roundtrip_support


class HistoryRootPreflight(unittest.TestCase):
    setup_store = roundtrip_support.MetadataRoundtripTests.setup_store
    export = roundtrip_support.MetadataRoundtripTests.export

    def test_actual_history_roots_reject_before_inventory(self):
        self.setup_store("google")
        source = self.export()
        real = self.root / "real"
        real.mkdir()
        for reserved in ("metadata", "assets"):
            for kind in ("file", "symlink"):
                for dry in (False, True):
                    name = reserved + kind + str(dry)
                    state = self.root / name
                    state.mkdir()
                    leaf = state / reserved
                    if kind == "file":
                        leaf.write_bytes(b"preserve")
                    else:
                        leaf.symlink_to(real, target_is_directory=True)
                    with (
                        self.subTest(root=reserved, kind=kind, dry_run=dry),
                        patch.object(
                            self.io,
                            "bounded_inventory",
                            side_effect=AssertionError(
                                "invalid history root hashed input"
                            ),
                        ),
                    ):
                        with self.assertRaisesRegex(ValueError, "directory|symlink"):
                            self.io.import_metadata(
                                self.root,
                                source,
                                self.target,
                                name + ".json",
                                state,
                                dry_run=dry,
                            )
                    self.assertFalse((self.root / (name + ".json")).exists())
                    if kind == "file":
                        self.assertEqual(leaf.read_bytes(), b"preserve")
                    else:
                        self.assertTrue(leaf.is_symlink())
        self.assertEqual(list(real.iterdir()), [])

    def test_unused_assets_root_does_not_block_metadata_only_import(self):
        self.setup_store("google")
        source = self.export()
        state = self.root / "history"
        state.mkdir()
        (state / "assets").write_bytes(b"preserve unrelated existing file")
        result = self.io.import_metadata(
            self.root, source, self.target, "listing.json", state, metadata_only=True
        )
        self.assertEqual(
            (state / "assets").read_bytes(), b"preserve unrelated existing file"
        )
        self.assertTrue((self.root / result["listing"]).exists())
