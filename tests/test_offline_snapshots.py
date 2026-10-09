import copy
import json
import unittest
from concurrent.futures import ThreadPoolExecutor

from offline_support import fixture, module


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.snapshots = module(self, "snapshots")
        self.metadata = module(self, "metadata")
        self.root, self.profile = fixture(self)
        self.remote = json.loads((self.root / "remote.json").read_text())

    def publish(self, data=b"public listing"):
        return self.snapshots.publish_snapshot(
            self.root / "history", {"type": "synthetic"}, {"text/name.txt": data}
        )

    def test_history_preserves_prior_versions_and_reuses_only_exact_content(self):
        first = self.publish()
        second = self.publish(b"new listing")
        self.assertNotEqual(first, second)
        self.assertEqual((first / "text/name.txt").read_bytes(), b"public listing")
        self.assertEqual(first, self.publish())

    def test_cache_file_and_manifest_cannot_be_changed_together(self):
        path = self.publish()
        (path / "text/name.txt").write_bytes(b"tampered")
        manifest = json.loads((path / "manifest.json").read_text())
        import hashlib

        manifest["files"]["text/name.txt"] = hashlib.sha256(b"tampered").hexdigest()
        (path / "manifest.json").write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, "address|manifest|cache"):
            self.snapshots.validate_snapshot(path)
        with self.assertRaises(ValueError):
            self.publish()

    def test_added_snapshot_file_is_rejected(self):
        path = self.publish()
        (path / "text/untracked.txt").write_text("unbound")
        with self.assertRaisesRegex(ValueError, "inventory"):
            self.snapshots.validate_snapshot(path)

    def test_concurrent_publication_reuses_only_validated_winner(self):
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(self.publish) for _ in range(2)]
            paths = [f.result() for f in futures]
        self.assertEqual(paths[0], paths[1])
        self.snapshots.validate_snapshot(paths[0])

    def test_private_fields_are_not_exported(self):
        self.remote["fields"]["en-US"]["demo_password"] = "synthetic-secret"
        with self.assertRaisesRegex(ValueError, "private|unsupported|field"):
            self.metadata.normalize_remote(self.remote, self.remote["target"])
        with self.assertRaisesRegex(ValueError, "credential"):
            self.snapshots.publish_snapshot(
                self.root / "history", {"type": "metadata"}, {".env": b"fake"}
            )

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
