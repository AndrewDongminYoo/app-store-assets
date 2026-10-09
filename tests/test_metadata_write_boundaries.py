"""B2 import/publication regressions written before the implementation."""

import copy
import hashlib
import json
import unittest

from offline_support import fixture, module, write_json
from test_offline_boundaries import snapshot_fixture


class MetadataWriteBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.root, self.profile = fixture(self)
        self.target = module("profiles").target_identity(
            self.profile["targets"]["production"]
        )
        self.record = {
            "schema_version": 1,
            "type": "metadata-snapshot",
            "target": self.target,
            "fields": {"en-US": {"description": "public"}},
            "images": {},
        }

    def test_4230952504_export_manifest_and_final_provenance_rejected_without_writes(
        self,
    ):
        for change in (
            "source-object",
            "source-not-digest",
            "unknown-header",
            "unknown-entry",
        ):
            with self.subTest(change=change):
                name = "editing-" + change
                path = snapshot_fixture(self.root / "history", self.record)
                module("metadata_io").export_metadata(
                    self.root, path, self.target, name
                )
                manifest_path = self.root / name / module("metadata_io").EXPORT_MANIFEST
                value = json.loads(manifest_path.read_text())
                if change == "source-object":
                    value["source_snapshot"] = {"api_token": "synthetic-only"}
                elif change == "source-not-digest":
                    value["source_snapshot"] = "not-a-digest"
                elif change == "unknown-header":
                    value["api_token"] = "synthetic-only"
                else:
                    value["fields"][0]["api_token"] = "synthetic-only"
                write_json(manifest_path, value)
                before = {
                    str(p.relative_to(self.root)): hashlib.sha256(
                        p.read_bytes()
                    ).hexdigest()
                    for p in self.root.rglob("*")
                    if p.is_file()
                }
                for dry in (True, False):
                    with self.subTest(dry_run=dry), self.assertRaises(ValueError):
                        module("metadata_io").import_metadata(
                            self.root,
                            name,
                            self.target,
                            "new-" + change + ".json",
                            "new-state",
                            dry_run=dry,
                        )
                after = {
                    str(p.relative_to(self.root)): hashlib.sha256(
                        p.read_bytes()
                    ).hexdigest()
                    for p in self.root.rglob("*")
                    if p.is_file()
                }
                self.assertEqual(before, after)

    def test_export_rejects_credential_url_before_new_destination(self):
        record = copy.deepcopy(self.record)
        record["fields"]["en-US"]["marketing_url"] = (
            "https://example.invalid/?api_key=synthetic"
        )
        path = snapshot_fixture(self.root / "history", record)
        for dry in (True, False):
            with self.subTest(dry_run=dry), self.assertRaises(ValueError):
                module("metadata_io").export_metadata(
                    self.root, path, self.target, "new-export", dry_run=dry
                )
        self.assertFalse((self.root / "new-export").exists())

    def test_final_metadata_history_roundtrip_has_validated_provenance(self):
        path = snapshot_fixture(self.root / "history", self.record)
        module("metadata_io").export_metadata(self.root, path, self.target, "editing")
        result = module("metadata_io").import_metadata(
            self.root, "editing", self.target, "new.json", "state"
        )
        manifest = module("snapshots").validate_snapshot(self.root / result["snapshot"])
        record = module("metadata").validate_public_metadata(
            manifest["record"], self.target
        )
        self.assertEqual(len(record["source_export"]), 64)
