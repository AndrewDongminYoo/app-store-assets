"""Entry, depth and aggregate byte bounds on every public directory walk."""

import hashlib
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from offline_support import fixture, module

from app_store_assets import records
from app_store_assets_local import staging
from app_store_assets_local.budgets import bounded_inventory

ENTRY = "exceeds entry bound"
DEPTH = "exceeds depth bound"
BYTES = "exceeds aggregate byte bound"
GREW = "regular-file/size contract"


class BoundedWalk(unittest.TestCase):
    def setUp(self):
        # Resolve once: the trusted root may not contain a symlinked ancestor.
        self.root = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, self.root)

    def limits(self, *, entries=10000, depth=16, file_bytes=records.FILE_LIMIT):
        stack = [
            patch.object(records, "WALK_ENTRY_LIMIT", entries),
            patch.object(records, "WALK_DEPTH_LIMIT", depth),
            patch.object(records, "FILE_LIMIT", file_bytes),
        ]
        for item in stack:
            item.start()
            self.addCleanup(item.stop)

    def write(self, relative, data=b"x"):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return relative

    def chain(self, levels, base=""):
        names = ["d%d" % index for index in range(levels)]
        (self.root / base).joinpath(*names).mkdir(parents=True, exist_ok=True)
        return "/".join(([base] if base else []) + names)

    def import_walk(self, names, total=1 << 20):
        return bounded_inventory(self.root, {name: total for name in names}, total)

    def stage(self, names):
        output = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, output)
        destination = output / "staged"
        expected = {
            name: hashlib.sha256((self.root / name).read_bytes()).hexdigest()
            for name in names
        }
        return destination, lambda: staging.stage_inventory(
            self.root, destination, expected
        )

    def grow_before_hash(self, names):
        """Grow each file to 6 bytes right before its digest is read."""
        original, order = records.digest_stream, iter(names)

        def grow(stream, *args, **kwargs):
            (self.root / next(order)).write_bytes(b"123456")
            return original(stream, *args, **kwargs)

        item = patch.object(records, "digest_stream", grow)
        item.start()
        self.addCleanup(item.stop)

    # Entry bound

    def test_tree_inventory_rejects_entries_over_bound(self):
        self.limits(entries=4)
        for name in "abcd":
            self.write(name)
        self.assertEqual(len(records.tree_inventory(self.root)), 4)
        (self.root / "empty").mkdir()
        with self.assertRaisesRegex(ValueError, ENTRY):
            records.tree_inventory(self.root)

    def test_tree_inventory_counts_excluded_root_names(self):
        self.limits(entries=2)
        self.write("manifest.json")
        self.write("a")
        self.assertEqual(
            list(records.tree_inventory(self.root, exclude_root=("manifest.json",))),
            ["a"],
        )
        self.write("b")
        with self.assertRaisesRegex(ValueError, ENTRY):
            records.tree_inventory(self.root, exclude_root=("manifest.json",))

    def test_inventory_shares_entry_bound_across_paths(self):
        # Two requested directories plus six walked files.
        self.limits(entries=8)
        for name in ("one/a", "one/b", "one/c", "two/a", "two/b", "two/c"):
            self.write(name)
        self.assertEqual(len(records.inventory(self.root, ["one", "two"])), 6)
        (self.root / "two/empty").mkdir()
        with self.assertRaisesRegex(ValueError, ENTRY):
            records.inventory(self.root, ["one", "two"])

    def test_inventory_counts_requested_file_paths_before_opening(self):
        self.limits(entries=2)
        names = [self.write(name, b"") for name in "ab"]
        self.assertEqual(list(records.inventory(self.root, names)), names)
        # The third path does not exist: the entry bound refuses it unopened.
        with self.assertRaisesRegex(ValueError, ENTRY):
            records.inventory(self.root, names + ["missing"])

    def test_import_walk_rejects_undeclared_empty_directories(self):
        self.limits(entries=4)
        names = [self.write(name) for name in ("a", "b", "c")]
        (self.root / "empty").mkdir()
        self.assertEqual(sorted(self.import_walk(names)), names)
        (self.root / "empty/nested").mkdir()
        with self.assertRaisesRegex(ValueError, ENTRY):
            self.import_walk(names)

    # Depth bound

    def test_tree_inventory_rejects_depth_over_bound(self):
        self.limits(depth=3)
        leaf = self.write(self.chain(3) + "/leaf")
        self.assertEqual(list(records.tree_inventory(self.root)), [leaf])
        self.chain(4)
        with self.assertRaisesRegex(ValueError, DEPTH):
            records.tree_inventory(self.root)

    def test_inventory_counts_depth_below_each_requested_path(self):
        self.limits(depth=2)
        leaf = self.write(self.chain(2, base="top") + "/leaf")
        self.assertEqual(list(records.inventory(self.root, ["top"])), [leaf])
        self.chain(3, base="top")
        with self.assertRaisesRegex(ValueError, DEPTH):
            records.inventory(self.root, ["top"])

    def test_import_walk_rejects_depth_over_bound(self):
        self.limits(depth=3)
        leaf = self.write(self.chain(3) + "/leaf")
        self.assertEqual(list(self.import_walk([leaf])), [leaf])
        self.chain(4)
        with self.assertRaisesRegex(ValueError, DEPTH):
            self.import_walk([leaf])

    def test_import_walk_rejects_deep_empty_tree_at_default_bound(self):
        leaf = self.write("leaf")
        self.chain(64)
        with self.assertRaisesRegex(ValueError, DEPTH):
            self.import_walk([leaf])

    # Aggregate byte bound

    def test_tree_inventory_rejects_aggregate_bytes_over_bound(self):
        self.limits(file_bytes=8)
        self.write("a", b"1234")
        self.write("b", b"5678")
        self.assertEqual(len(records.tree_inventory(self.root)), 2)
        self.assertEqual(len(records.tree_inventory(self.root, total_limit=8)), 2)
        self.write("c", b"9")
        with self.assertRaisesRegex(ValueError, BYTES):
            records.tree_inventory(self.root)
        with self.assertRaisesRegex(ValueError, BYTES):
            records.tree_inventory(self.root, total_limit=100)

    def test_inventory_shares_aggregate_bytes_across_paths(self):
        self.limits(file_bytes=8)
        self.write("a", b"1234")
        self.write("tree/b", b"5678")
        self.assertEqual(len(records.inventory(self.root, ["a", "tree"])), 2)
        self.write("c", b"9")
        with self.assertRaisesRegex(ValueError, BYTES):
            records.inventory(self.root, ["a", "c", "tree"])

    def test_import_walk_rejects_aggregate_bytes_over_bound(self):
        self.limits(file_bytes=8)
        names = [self.write("a", b"1234"), self.write("b", b"5678")]
        self.assertEqual(sorted(self.import_walk(names)), names)
        names.append(self.write("c", b"9"))
        with self.assertRaisesRegex(ValueError, BYTES):
            self.import_walk(names)

    def test_tree_inventory_does_not_hash_growth_beyond_charged_size(self):
        self.limits(file_bytes=8)
        names = [self.write(name, b"") for name in "abc"]
        self.grow_before_hash(names)
        with self.assertRaisesRegex(ValueError, GREW):
            records.tree_inventory(self.root)

    def test_inventory_does_not_hash_growth_beyond_charged_size(self):
        self.limits(file_bytes=8)
        names = [self.write(name, b"") for name in "abc"]
        self.grow_before_hash(names)
        with self.assertRaisesRegex(ValueError, GREW):
            records.inventory(self.root, names)

    # Writers reject an over-bound tree before writing it

    def test_staging_rejects_files_over_entry_bound_before_writing(self):
        self.limits(entries=2)
        destination, run = self.stage([self.write("a"), self.write("b")])
        run()
        self.assertEqual(sorted(records.tree_inventory(destination)), ["a", "b"])
        destination, run = self.stage(["a", "b", self.write("c")])
        with self.assertRaisesRegex(ValueError, ENTRY):
            run()
        self.assertFalse(destination.exists())

    def test_staging_counts_parent_directories_as_entries(self):
        self.limits(entries=3)
        destination, run = self.stage([self.write("a/b"), self.write("a/c")])
        run()
        destination, run = self.stage(["a/b", "a/c", self.write("d/e")])
        with self.assertRaisesRegex(ValueError, ENTRY):
            run()
        self.assertFalse(destination.exists())

    def test_staging_rejects_depth_over_bound_before_writing(self):
        self.limits(depth=3)
        destination, run = self.stage([self.write(self.chain(3) + "/leaf")])
        run()
        destination, run = self.stage([self.write(self.chain(4) + "/leaf")])
        with self.assertRaisesRegex(ValueError, DEPTH):
            run()
        self.assertFalse(destination.exists())

    def test_snapshot_publish_counts_manifest_before_writing(self):
        root, profile = fixture(self)
        record = {
            "schema_version": 1,
            "type": "metadata-snapshot",
            "target": module("profiles").target_identity(
                profile["targets"]["production"]
            ),
            "fields": {},
            "images": {},
        }
        publish = module("publisher").publish_snapshot
        self.limits(entries=2)
        accepted, rejected = root / "accepted", root / "rejected"
        accepted.mkdir()
        rejected.mkdir()
        publish(accepted, record, {"notes.txt": b"Public"})
        with self.assertRaisesRegex(ValueError, ENTRY):
            publish(rejected, record, {"a.txt": b"Public", "b.txt": b"Public"})
        self.assertEqual(list(rejected.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
