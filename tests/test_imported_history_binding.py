"""Imported listings bind their changelogs to the named history snapshot."""

import json
import unittest

from offline_support import fixture, module
from test_offline_boundaries import snapshot_fixture


class ImportedHistoryBinding(unittest.TestCase):
    def test_tampered_history_changelog_rejects_after_import(self):
        root, profile = fixture(self)
        target = module("profiles").target_identity(profile["targets"]["production"])
        record = {
            "schema_version": 1,
            "type": "metadata-snapshot",
            "target": target,
            "fields": {"en-US": {"release_notes": "Public notes"}},
            "images": {},
        }
        snapshot = snapshot_fixture(root / "downloads", record)
        io = module("metadata_io")
        source = io.export_metadata(root, snapshot, target, "editing")
        result = io.import_metadata(
            root, source, target, "listing.json", "state", metadata_only=True
        )
        listing = json.loads((root / result["listing"]).read_text())
        # Only the history snapshot may vouch for the changelog bytes.
        listing.pop("release_notes")
        listing["fields"]["en-US"].pop("release_notes", None)
        metadata = module("metadata")
        clean = metadata.resolve_changelogs(root, listing, target, {})
        self.assertEqual(clean["release_notes"], {"en-US": "Public notes"})
        note = root / result["changelogs"]["en-US"]
        note.chmod(0o644)
        note.write_text("Tampered notes")
        with self.assertRaisesRegex(ValueError, "snapshot"):
            metadata.resolve_changelogs(root, listing, target, {})


if __name__ == "__main__":
    unittest.main()
