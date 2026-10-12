"""Changelog content bases and unselected Google releases; synthetic inputs only."""

import json
import unittest

from offline_support import fixture, module


class ChangelogContentBase(unittest.TestCase):
    def test_ordinary_64_character_directory_is_not_inferred_as_snapshot(self):
        root, profile = fixture(self)
        target = module("profiles").target_identity(profile["targets"]["production"])
        record = json.loads((root / "metadata/listing.json").read_text())
        name = "c" * 64 + "/notes.txt"
        (root / name).parent.mkdir()
        (root / name).write_text("Public notes")
        record["changelogs"] = {"en-US": name}
        result = module("metadata").resolve_changelogs(root, record, target, {})
        self.assertEqual(result["release_notes"], {"en-US": "Public notes"})


class UnselectedGoogleRelease(unittest.TestCase):
    def setUp(self):
        self.root, self.profile = fixture(self, "google")
        self.record = json.loads((self.root / "remote.json").read_text())
        self.record["releases"] = [
            {"version_codes": ["8"], "notes": {"en-US": "Older build notes"}}
        ]

    def test_unselected_track_releases_keep_top_level_notes(self):
        self.record["release_notes"] = {"en-US": "Selected notes"}
        self.assertEqual(
            module("metadata").selected_notes(self.record),
            {"en-US": "Selected notes"},
        )

    def test_unselected_track_releases_accept_changelog_notes(self):
        (self.root / "notes.txt").write_text("Changelog notes")
        self.record["changelogs"] = {"en-US": "notes.txt"}
        result = module("metadata").resolve_changelogs(
            self.root, self.record, self.record["target"], {}
        )
        self.assertEqual(result["release_notes"], {"en-US": "Changelog notes"})
        self.assertEqual(result["releases"], self.record["releases"])

    def test_selected_track_release_still_rejects_conflicting_notes(self):
        self.record["releases"].append(
            {"version_codes": ["9"], "notes": {"en-US": "Release notes"}}
        )
        self.record["release_notes"] = {"en-US": "Different notes"}
        with self.assertRaisesRegex(ValueError, "conflicting"):
            module("metadata").selected_notes(self.record)


if __name__ == "__main__":
    unittest.main()
