"""Hosted follow-up: notes survive roundtrips; invalid roots prevent captures."""

import copy
import json
import unittest
from unittest.mock import patch

from offline_support import fixture, module
from test_offline_boundaries import snapshot_fixture


class FollowupMetadataPreservation(unittest.TestCase):
    def setUp(self):
        self.root, profile = fixture(self)
        self.target = module("profiles").target_identity(
            profile["targets"]["production"]
        )
        self.record = {
            "schema_version": 1,
            "type": "metadata-snapshot",
            "target": self.target,
            "fields": {"en-US": {"description": "public"}},
            "images": {},
        }

    def test_apple_top_level_notes_survive_export_and_import(self):
        for inline in (False, True):
            with self.subTest(duplicate_field=inline):
                record = copy.deepcopy(self.record)
                record["release_notes"] = {"en-US": "Public notes", "fr-FR": ""}
                if inline:
                    record["fields"]["en-US"]["release_notes"] = "Public notes"
                snapshot = snapshot_fixture(self.root / "downloads", record)
                source = self.root / ("editing-" + str(inline))
                module("metadata_io").export_metadata(
                    self.root, snapshot, self.target, source
                )
                self.assertEqual(
                    (source / "en-US/release_notes.txt").read_text(), "Public notes"
                )
                result = module("metadata_io").import_metadata(
                    self.root,
                    source,
                    self.target,
                    "listing-" + str(inline) + ".json",
                    "state-" + str(inline),
                    metadata_only=True,
                )
                listing = json.loads((self.root / result["listing"]).read_text())
                self.assertEqual(listing["release_notes"], record["release_notes"])
                self.assertEqual(
                    listing["fields"]["en-US"]["release_notes"], "Public notes"
                )

    def test_conflicting_apple_notes_reject_export_before_publication(self):
        record = copy.deepcopy(self.record)
        record["release_notes"] = {"en-US": "Top-level public notes"}
        record["fields"]["en-US"]["release_notes"] = "Different public notes"
        snapshot = snapshot_fixture(self.root / "downloads", record)
        for dry in (False, True):
            with (
                self.subTest(dry_run=dry),
                self.assertRaisesRegex(ValueError, "conflicting"),
            ):
                module("metadata_io").export_metadata(
                    self.root, snapshot, self.target, "blocked", dry_run=dry
                )
        self.assertFalse((self.root / "blocked").exists())

    def test_invalid_snapshot_roots_prevent_capture_and_image_validation(self):
        publisher = module("publisher")
        source = self.root / "public.txt"
        source.write_text("public bytes")
        real = self.root / "real"
        real.mkdir()
        alias = self.root / "alias"
        alias.symlink_to(real, target_is_directory=True)
        snapshot = snapshot_fixture(self.root / "downloads", self.record)
        for root in (
            self.root / ".env/history",
            alias / "history",
            snapshot / "history",
        ):
            with (
                self.subTest(root=root),
                patch.object(
                    publisher,
                    "capture_bytes",
                    side_effect=AssertionError("invalid output captured source"),
                ),
                patch.object(
                    publisher,
                    "snapshot_manifest",
                    side_effect=AssertionError("invalid output decoded images"),
                ),
            ):
                with self.assertRaises(ValueError):
                    publisher.publish_snapshot(
                        root, self.record, {"public.txt": source}
                    )
        self.assertEqual(list(real.iterdir()), [])
