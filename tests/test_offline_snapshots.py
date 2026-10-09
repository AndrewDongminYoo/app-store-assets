import copy
import json
import unittest

from offline_support import fixture, module
from test_offline_boundaries import snapshot_fixture


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.snapshots = module(self, "snapshots")
        self.metadata = module(self, "metadata")
        self.root, self.profile = fixture(self)
        self.remote = json.loads((self.root / "remote.json").read_text())

    def publish(self, data=b"public listing"):
        return snapshot_fixture(
            self.root / "history", self.remote, {"text/name.txt": data}
        )

    def test_cache_file_and_manifest_cannot_be_changed_together(self):
        path = self.publish()
        (path / "text/name.txt").write_bytes(b"tampered")
        manifest = json.loads((path / "manifest.json").read_text())
        import hashlib

        manifest["files"]["text/name.txt"] = hashlib.sha256(b"tampered").hexdigest()
        (path / "manifest.json").write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, "address|manifest|cache"):
            self.snapshots.validate_snapshot(path)

    def test_added_snapshot_file_is_rejected(self):
        path = self.publish()
        (path / "text/untracked.txt").write_text("unbound")
        with self.assertRaisesRegex(ValueError, "inventory"):
            self.snapshots.validate_snapshot(path)

    def test_private_fields_are_not_exported(self):
        self.remote["fields"]["en-US"]["demo_password"] = "synthetic-secret"
        with self.assertRaisesRegex(ValueError, "private|unsupported|field"):
            self.metadata.normalize_remote(self.remote, self.remote["target"])

    def test_diff_reports_text_change_and_image_reordering(self):
        before = self.metadata.normalize_remote(self.remote, self.remote["target"])
        before["images"] = {"en-US": {"APP_IPHONE_65": [{"id": "a"}, {"id": "b"}]}}
        after = copy.deepcopy(before)
        after["fields"]["en-US"]["description"] = "edited"
        after["images"]["en-US"]["APP_IPHONE_65"].reverse()
        changes = self.metadata.metadata_diff(before, after)
        self.assertIn(
            {
                "path": "fields.en-US.description",
                "kind": "change",
                "before": "Approved description",
                "after": "edited",
            },
            changes,
        )
        self.assertTrue(
            any(
                c["path"] == "images.en-US.APP_IPHONE_65" and c["kind"] == "reorder"
                for c in changes
            )
        )

    def test_diff_rejects_account_or_version_conflict(self):
        before = self.metadata.normalize_remote(self.remote, self.remote["target"])
        after = copy.deepcopy(before)
        after["target"]["version"]["name"] = "other"
        with self.assertRaisesRegex(ValueError, "target"):
            self.metadata.metadata_diff(before, after)
