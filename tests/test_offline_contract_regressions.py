"""Adversarial regressions from independent B review; temporary public inputs only."""

import copy
import io
import json
import unittest
from unittest.mock import patch

from offline_support import container, fixture, module, write_json
from test_offline_boundaries import snapshot_fixture


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
        snapshot = snapshot_fixture(self.root / "history", record, {})
        directory = None  # Reader fixture needs no editing/export implementation.
        return snapshot, directory, record

    def test_cli_diff_rejects_tampered_snapshot_manifest(self):
        import contextlib

        snapshot, _, record = self.editing()
        value = json.loads((snapshot / "manifest.json").read_text())
        value["record"]["fields"]["en-US"]["description"] = "Tampered"
        write_json(snapshot / "manifest.json", value)
        write_json(self.root / "after.json", record)
        with (
            contextlib.redirect_stdout(io.StringIO()),
            contextlib.redirect_stderr(io.StringIO()),
        ):
            code = module("cli").main(
                [
                    "diff",
                    "--root",
                    str(self.root),
                    "--target",
                    "production",
                    "--before",
                    str(snapshot.relative_to(self.root) / "manifest.json"),
                    "--after",
                    "after.json",
                ]
            )
        self.assertEqual(code, 2)

    def test_supplied_snapshot_schema_private_and_unsupported_fields_rejected(self):
        path = self.root / "remote.json"
        original = json.loads(path.read_text())
        cases = [
            {"schema_version": 2},
            {"type": "unsupported"},
            {"api_token": "synthetic"},
            {
                "fields": {
                    "en-US": {
                        "description": "Original",
                        "private_demo_password": "synthetic",
                    }
                }
            },
        ]
        for change in cases:
            with self.subTest(change=change):
                write_json(path, original | change)
                with self.assertRaisesRegex(
                    ValueError, "schema|type|public|private|unsupported|unknown"
                ):
                    module("planning").make_plan(
                        self.root, "store-upload.json", "production", "binary"
                    )
        write_json(path, original)

    def test_artifact_kind_uses_hash_bound_capture_despite_swap_and_restore(self):
        self.root, self.profile = fixture(self, "google", "apk")
        path = self.root / "artifacts/app.apk"
        container(path, "aab")
        record = json.loads((self.root / "artifact.json").read_text())
        record["sha256"] = module("records").file_digest(path)
        write_json(self.root / "artifact.json", record)
        original = path.read_bytes()
        temp = self.root / "substitute.apk"
        container(temp, "apk")
        substitution = temp.read_bytes()
        artifacts = module("artifacts")
        real_kind = artifacts.container_kind

        def swap(observed):
            path.write_bytes(substitution)
            try:
                return real_kind(observed)
            finally:
                path.write_bytes(original)

        with patch.object(artifacts, "container_kind", side_effect=swap):
            with self.assertRaisesRegex(ValueError, "kind|container"):
                module("planning").make_plan(
                    self.root, "store-upload.json", "production", "binary"
                )
        self.assertEqual(path.read_bytes(), original)

    def test_google_selected_release_note_change_is_visible_in_diff(self):
        self.root, self.profile = fixture(self, "google")
        target = module("profiles").target_identity(
            self.profile["targets"]["production"]
        )
        before = {
            "schema_version": 1,
            "type": "metadata-snapshot",
            "target": target,
            "fields": {},
            "images": {},
            "releases": [
                {"version_codes": ["9"], "notes": {"en-US": "Original"}},
                {"version_codes": ["8"], "notes": {"en-US": "Other build"}},
            ],
        }
        after = copy.deepcopy(before)
        after["releases"][0]["notes"]["en-US"] = "Changed"
        changes = module("metadata").metadata_diff(before, after)
        self.assertEqual(
            changes,
            [
                {
                    "path": "release_notes.en-US",
                    "kind": "change",
                    "before": "Original",
                    "after": "Changed",
                }
            ],
        )
        after = copy.deepcopy(before)
        after["releases"][1]["notes"]["en-US"] = "Unselected build"
        self.assertEqual(module("metadata").metadata_diff(before, after), [])

    def test_cli_diff_captures_local_changelog_content(self):
        import contextlib

        self.root, self.profile = fixture(self, "google")
        target = module("profiles").target_identity(
            self.profile["targets"]["production"]
        )
        before = {
            "schema_version": 1,
            "type": "metadata-snapshot",
            "target": target,
            "fields": {},
            "images": {},
            "releases": [{"version_codes": ["9"], "notes": {"en-US": "Original"}}],
        }
        after = {
            "schema_version": 1,
            "type": "metadata",
            "target": target,
            "fields": {},
            "images": {},
            "changelogs": {"en-US": "metadata/en-US/changelogs/9.txt"},
        }
        write_json(self.root / "before.json", before)
        write_json(self.root / "after.json", after)
        (self.root / "metadata/en-US/changelogs/9.txt").write_text("Changed")
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = module("cli").main(
                [
                    "diff",
                    "--root",
                    str(self.root),
                    "--target",
                    "production",
                    "--before",
                    "before.json",
                    "--after",
                    "after.json",
                ]
            )
        self.assertEqual(code, 0)
        self.assertEqual(
            json.loads(out.getvalue()),
            [
                {
                    "path": "release_notes.en-US",
                    "kind": "change",
                    "before": "Original",
                    "after": "Changed",
                }
            ],
        )

    def test_public_record_nested_types_and_private_inventory_rejected(self):
        path = self.root / "remote.json"
        original = json.loads(path.read_text())
        cases = [
            {
                "images": {
                    "en-US": {"APP_IPHONE_65": [{"id": {"demo_password": "synthetic"}}]}
                }
            },
            {"inputs": {".env": "synthetic"}},
            {"binary": {"api_token": "synthetic"}},
            {"revision": {"private": "synthetic"}},
        ]
        for change in cases:
            with self.subTest(change=change):
                write_json(path, original | change)
                with self.assertRaisesRegex(
                    ValueError, "public|private|unsupported|invalid|hash|binary"
                ):
                    module("planning").make_plan(
                        self.root, "store-upload.json", "production", "metadata"
                    )

    def test_existing_empty_apple_snapshot_fields_are_not_proposed_clears(self):
        path = self.root / "remote.json"
        value = json.loads(path.read_text())
        value["fields"]["en-US"].update(support_url="", privacy_url="", name="")
        write_json(path, value)
        plan = module("planning").make_plan(
            self.root, "store-upload.json", "production", "metadata"
        )
        self.assertEqual(
            plan["payload"]["listing"]["fields"]["en-US"],
            {"description": "Approved description"},
        )
