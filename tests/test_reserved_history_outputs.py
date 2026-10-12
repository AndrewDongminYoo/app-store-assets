"""Keep ordinary listings outside content-addressed history namespaces."""

import unittest

from offline_support import fixture, module
from test_offline_boundaries import snapshot_fixture


class ReservedHistoryOutputs(unittest.TestCase):
    def test_real_and_dry_import_reject_listings_beneath_either_history_root(self):
        root, profile = fixture(self)
        target = module("profiles").target_identity(profile["targets"]["production"])
        record = {
            "schema_version": 1,
            "type": "metadata-snapshot",
            "target": target,
            "fields": {"en-US": {"description": "Public description"}},
            "images": {},
        }
        snapshot = snapshot_fixture(root / "snapshots", record)
        editing = module("metadata_io").export_metadata(
            root, snapshot, target, "editing"
        )
        for namespace in ("assets", "metadata"):
            for dry_run in (True, False):
                with self.subTest(namespace=namespace, dry_run=dry_run):
                    state = root / (namespace + ("-dry" if dry_run else "-real"))
                    output = state / namespace / ("a" * 64) / "manifest.json"
                    with self.assertRaisesRegex(ValueError, "reserved history"):
                        module("metadata_io").import_metadata(
                            root,
                            editing,
                            target,
                            output,
                            state,
                            metadata_only=True,
                            dry_run=dry_run,
                        )
                    self.assertFalse(state.exists())
                    self.assertFalse(output.exists())
