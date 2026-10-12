"""Imported listings keep notes inline and stay bound to their history snapshot."""

import json
import unittest

from offline_support import fixture, module
from test_offline_boundaries import snapshot_fixture


class ImportedHistoryBinding(unittest.TestCase):
    def test_import_listing_keeps_notes_inline_and_binds_history(self):
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
        self.assertNotIn("changelogs", listing)
        self.assertEqual(listing["release_notes"], {"en-US": "Public notes"})
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
