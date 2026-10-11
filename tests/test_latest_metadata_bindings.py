"""Current review regressions use synthetic local inputs only."""

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
