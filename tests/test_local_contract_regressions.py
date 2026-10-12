"""Adversarial regressions from independent B review; temporary public inputs only."""

import json
import unittest

from offline_support import fixture, module


class OfflineContractRegressions(unittest.TestCase):
    def setUp(self):
        self.root, self.profile = fixture(self)
        self.target = module("profiles").target_identity(
            self.profile["targets"]["production"]
        )

    def editing(self):
        record = {
            "schema_version": 1,
            "type": "metadata-snapshot",
            "target": self.target,
            "fields": {"en-US": {"description": "Original"}},
            "images": {},
        }
        snapshot = module("publisher").publish_snapshot(
            self.root / "history", record, {}
        )
        directory = module("metadata_io").export_metadata(
            self.root, snapshot, self.target, "editing"
        )
        return snapshot, directory, record

    def test_import_output_and_history_cannot_mutate_prior_snapshot(self):
        snapshot, editing, _ = self.editing()
        for output, history in (
            (snapshot / "new.json", self.root / "import-history"),
            (self.root / "new.json", snapshot / "new-history"),
        ):
            with self.subTest(output=str(output), history=str(history)):
                with self.assertRaisesRegex(ValueError, "snapshot|immutable"):
                    module("metadata_io").import_metadata(
                        self.root, editing, self.target, output, history
                    )
                module("snapshots").validate_snapshot(snapshot)
                self.assertFalse(output.exists())

    def test_export_cannot_mutate_different_snapshot(self):
        snapshot, _, record = self.editing()
        other = module("publisher").publish_snapshot(
            self.root / "other", dict(record, revision="other"), {}
        )
        with self.assertRaisesRegex(ValueError, "snapshot|immutable"):
            module("metadata_io").export_metadata(
                self.root, snapshot, self.target, other / "new-export"
            )
        module("snapshots").validate_snapshot(other)

    def test_snapshot_publication_cannot_invalidate_existing_snapshot(self):
        snapshot, _, _ = self.editing()
        with self.assertRaisesRegex(ValueError, "snapshot|immutable"):
            module("publisher").publish_snapshot(
                snapshot / "nested-history",
                json.loads((snapshot / "manifest.json").read_text())["record"],
                {},
            )
        module("snapshots").validate_snapshot(snapshot)

    def test_google_import_rejects_overlong_notes_before_any_publication(self):
        self.root, self.profile = fixture(self, "google")
        target = module("profiles").target_identity(
            self.profile["targets"]["production"]
        )
        record = {
            "schema_version": 1,
            "type": "metadata-snapshot",
            "target": target,
            "fields": {"en-US": {"full_description": "Public"}},
            "images": {},
            "releases": [{"version_codes": ["9"], "notes": {"en-US": "Original"}}],
        }
        snapshot = module("publisher").publish_snapshot(
            self.root / "history", record, {}
        )
        editing = module("metadata_io").export_metadata(
            self.root, snapshot, target, "editing"
        )
        (editing / "en-US/changelogs/9.txt").write_text("x" * 501)
        for dry_run in (True, False):
            with self.subTest(dry_run=dry_run):
                with self.assertRaisesRegex(
                    ValueError, "release-notes.*limit|limit.*release-notes"
                ):
                    module("metadata_io").import_metadata(
                        self.root,
                        editing,
                        target,
                        "new.json",
                        "new-history",
                        dry_run=dry_run,
                    )
                self.assertFalse((self.root / "new-history").exists())
                self.assertFalse((self.root / "new.json").exists())
        (editing / "en-US/changelogs/9.txt").write_text("x" * 500)
        result = module("metadata_io").import_metadata(
            self.root, editing, target, "new.json", "new-history"
        )
        listing = module("cli").metadata_input(self.root, result["listing"], target)
        self.assertEqual(len(listing["release_notes"]["en-US"]), 500)
