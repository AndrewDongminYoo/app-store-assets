"""Snapshot changelogs survive export; local publication keeps notes inline."""

import unittest

from offline_support import fixture, module
from test_offline_boundaries import snapshot_fixture


class LocalChangelogContract(unittest.TestCase):
    def setUp(self):
        self.root, profile = fixture(self, "google")
        self.target = module("profiles").target_identity(
            profile["targets"]["production"]
        )
        self.record = {
            "schema_version": 1,
            "type": "metadata-snapshot",
            "target": self.target,
            "fields": {"en-US": {"full_description": "Public"}},
            "images": {},
            "changelogs": {"en-US": "notes.txt"},
        }

    def test_export_reads_changelogs_from_the_snapshot(self):
        snapshot = snapshot_fixture(
            self.root / "downloads", self.record, {"notes.txt": b"Snapshot notes"}
        )
        editing = module("metadata_io").export_metadata(
            self.root, snapshot, self.target, "editing"
        )
        build = self.target["version"]["build"]
        note = editing / "en-US/changelogs" / (build + ".txt")
        self.assertEqual(note.read_text(), "Snapshot notes")

    def test_export_rejects_a_snapshot_changelog_missing_from_its_inventory(self):
        snapshot = snapshot_fixture(self.root / "downloads", self.record, {})
        for dry in (True, False):
            with self.subTest(dry_run=dry), self.assertRaises(ValueError):
                module("metadata_io").export_metadata(
                    self.root, snapshot, self.target, "editing", dry_run=dry
                )
        self.assertFalse((self.root / "editing").exists())

    def test_local_publication_rejects_changelog_references(self):
        state = self.root / "state"
        state.mkdir()
        with self.assertRaisesRegex(ValueError, "inline"):
            module("publisher").publish_snapshot(
                state, self.record, {"notes.txt": b"Snapshot notes"}
            )
        self.assertEqual(list(state.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
