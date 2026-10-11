"""Current review regressions use synthetic local inputs only."""

import copy
import json
import unittest

from offline_support import fixture, module, write_json
from test_offline_boundaries import snapshot_fixture


class LatestReviewRegressions(unittest.TestCase):
    def setUp(self):
        self.root, self.profile = fixture(self, "google")

    def notes_record(self, inline):
        record = json.loads((self.root / "metadata/listing.json").read_text())
        record.update(
            release_notes=inline,
            changelogs={"en-US": "metadata/en-US/changelogs/9.txt"},
        )
        return record

    def test_inline_and_file_notes_merge_and_bind_in_plan(self):
        record = self.notes_record({"fr-FR": "Inline approved notes"})
        write_json(self.root / "metadata/listing.json", record)
        plan = module("planning").make_plan(
            self.root, "store-upload.json", "production", "metadata"
        )
        self.assertEqual(
            plan["payload"]["release_notes"],
            {"fr-FR": "Inline approved notes", "en-US": "Approved notes\n"},
        )
        self.assertIn("metadata/en-US/changelogs/9.txt", plan["payload"]["inputs"])

    def test_duplicate_notes_accept_equal_text_and_reject_conflicts(self):
        for note in ("", "Different", "Approved notes\n"):
            with self.subTest(note=note):
                record = self.notes_record({"en-US": note})
                if note == "Approved notes\n":
                    clean = module("metadata").resolve_changelogs(
                        self.root, record, record["target"], {}
                    )
                    self.assertEqual(clean["release_notes"], {"en-US": note})
                else:
                    with self.assertRaisesRegex(ValueError, "conflicting"):
                        module("metadata").resolve_changelogs(
                            self.root, record, record["target"], {}
                        )

    def test_snapshot_notes_preserve_inline_locales(self):
        record = json.loads((self.root / "remote.json").read_text())
        record.update(
            release_notes={"fr-FR": "Inline remote notes"},
            changelogs={"en-US": "notes.txt"},
        )
        folder = snapshot_fixture(
            self.root / "history", record, {"notes.txt": b"File notes"}
        )
        clean = module("cli").metadata_input(
            self.root,
            (folder / "manifest.json").relative_to(self.root).as_posix(),
            record["target"],
        )
        self.assertEqual(
            clean["release_notes"],
            {"fr-FR": "Inline remote notes", "en-US": "File notes"},
        )

    def test_selected_google_release_merges_changelog_locales(self):
        record = self.notes_record({"fr-FR": "Selected notes"})
        record["releases"] = [
            {"version_codes": ["9"], "notes": {"fr-FR": "Selected notes"}},
            {"version_codes": ["8"], "notes": {"de-DE": "Other release"}},
        ]
        original = copy.deepcopy(record)
        expected = {"fr-FR": "Selected notes", "en-US": "Approved notes\n"}
        clean = module("metadata").resolve_changelogs(
            self.root, record, record["target"], {}
        )
        self.assertEqual(clean["release_notes"], expected)
        self.assertEqual(module("metadata").selected_notes(clean), expected)
        self.assertEqual(clean["releases"][0]["notes"], expected)
        self.assertEqual(clean["releases"][1], record["releases"][1])
        self.assertEqual(record, original)
        write_json(self.root / "metadata/listing.json", record)
        plan = module("planning").make_plan(
            self.root, "store-upload.json", "production", "metadata"
        )
        self.assertEqual(plan["payload"]["release_notes"], expected)
        self.assertIn("metadata/en-US/changelogs/9.txt", plan["payload"]["inputs"])
        for inline in ({"fr-FR": "Different"}, {"de-DE": "Unbound extra"}):
            with self.subTest(inline=inline):
                bad = copy.deepcopy(record)
                bad["release_notes"] = inline
                with self.assertRaisesRegex(ValueError, "conflicting"):
                    module("metadata").resolve_changelogs(
                        self.root, bad, bad["target"], {}
                    )
        bad = copy.deepcopy(record)
        bad["changelogs"] = {"fr-FR": "metadata/en-US/changelogs/9.txt"}
        with self.assertRaisesRegex(ValueError, "conflicting"):
            module("metadata").resolve_changelogs(self.root, bad, bad["target"], {})

    def test_selected_release_without_notes_accepts_bound_changelog(self):
        for existing in (
            {"version_codes": ["9"]},
            {"version_codes": ["9"], "notes": {}},
        ):
            with self.subTest(existing=existing):
                record = self.notes_record({})
                record["releases"] = [existing]
                original = copy.deepcopy(record)
                clean = module("metadata").resolve_changelogs(
                    self.root, record, record["target"], {}
                )
                expected = {"en-US": "Approved notes\n"}
                self.assertEqual(module("metadata").selected_notes(clean), expected)
                self.assertEqual(record, original)
