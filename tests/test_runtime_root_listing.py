"""The runtime root listing is charged against the shared walk entry bound."""

import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app_store_assets import identity, records

ENTRY = "exceeds entry bound"


class RuntimeRootListing(unittest.TestCase):
    def setUp(self):
        # Resolve once: the runtime root may not contain a symlinked ancestor.
        self.root = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, self.root)
        # Only assets.py and a.py are inventory inputs; notes.txt is root-only.
        for name in ("assets.py", "a.py", "notes.txt"):
            (self.root / name).write_bytes(b"x")

    def limit(self, entries):
        item = patch.object(records, "WALK_ENTRY_LIMIT", entries)
        item.start()
        self.addCleanup(item.stop)

    def test_root_listing_and_walk_at_shared_bound_are_accepted(self):
        # Three root entries plus two counted inventory paths.
        self.limit(5)
        self.assertEqual(
            sorted(identity.runtime_inventory(self.root)), ["a.py", "assets.py"]
        )

    def test_root_listing_and_walk_share_one_entry_bound(self):
        # Each stage fits the bound alone; only their total exceeds it.
        self.limit(4)
        self.assertEqual(
            sorted(records.inventory(self.root, ["a.py", "assets.py"])),
            ["a.py", "assets.py"],
        )
        with patch.object(identity.os, "stat", wraps=os.stat) as spy:
            with self.assertRaisesRegex(ValueError, ENTRY):
                identity.runtime_inventory(self.root)
        # The root listing completed, so the walk charged the excess entry.
        self.assertGreater(spy.call_count, 0)

    def test_root_listing_over_bound_rejects_before_any_stat(self):
        # The extra root entry is never an inventory input, so only the root
        # listing can charge it against the bound.
        (self.root / "b.txt").write_bytes(b"x")
        self.limit(3)
        with patch.object(identity.os, "stat", wraps=os.stat) as spy:
            with self.assertRaisesRegex(ValueError, ENTRY):
                identity.runtime_inventory(self.root)
        self.assertEqual(spy.call_count, 0)


if __name__ == "__main__":
    unittest.main()
