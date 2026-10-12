"""Changelog content bases and unselected Google releases; synthetic inputs only."""

import json
import unittest

from offline_support import fixture, module, write_json
from test_offline_boundaries import snapshot_fixture


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


class NamedSourceSnapshot(unittest.TestCase):
    def setUp(self):
        self.root, profile = fixture(self)
        self.target = module("profiles").target_identity(
            profile["targets"]["production"]
        )
        history = {
            "schema_version": 1,
            "type": "metadata-snapshot",
            "target": self.target,
            "fields": {},
            "images": {},
        }
        folder = snapshot_fixture(
            self.root / "state", history, {"en-US/notes.txt": b"History notes"}
        )
        self.note = folder / "en-US/notes.txt"
        self.record = json.loads((self.root / "metadata/listing.json").read_text())
        manifest = folder / "manifest.json"
        self.record.update(
            source_snapshot=manifest.relative_to(self.root).as_posix(),
            changelogs={"en-US": self.note.relative_to(self.root).as_posix()},
        )

    def resolve(self):
        return module("metadata").resolve_changelogs(
            self.root, self.record, self.target, {}
        )

    def test_named_source_snapshot_vouches_for_its_changelog(self):
        self.assertEqual(self.resolve()["release_notes"], {"en-US": "History notes"})

    def test_tampered_named_source_snapshot_rejects(self):
        self.note.write_text("Tampered notes")
        with self.assertRaisesRegex(ValueError, "snapshot"):
            self.resolve()

    def test_changelog_outside_the_named_snapshot_rejects(self):
        (self.root / "notes.txt").write_text("Unrelated notes")
        self.record["changelogs"] = {"en-US": "notes.txt"}
        with self.assertRaisesRegex(ValueError, "named source snapshot"):
            self.resolve()

    def test_source_snapshot_without_changelogs_is_bound_into_the_plan(self):
        self.record.pop("changelogs")
        write_json(self.root / "metadata/listing.json", self.record)
        planning = module("planning")
        plan = planning.make_plan(
            self.root, "store-upload.json", "production", "metadata"
        )
        self.assertIn(
            self.note.relative_to(self.root).as_posix(), plan["payload"]["inputs"]
        )
        self.note.write_text("Tampered notes")
        with self.assertRaises(ValueError):
            planning.verify_plan(self.root, plan)

    def test_source_snapshot_must_name_a_manifest(self):
        self.record["source_snapshot"] = self.record["changelogs"]["en-US"]
        with self.assertRaisesRegex(ValueError, "manifest"):
            self.resolve()


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
