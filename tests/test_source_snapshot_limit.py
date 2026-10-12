"""A named source snapshot is validated under the aggregate byte limit."""

import json
import unittest
from unittest.mock import patch

from offline_support import fixture, module
from test_offline_boundaries import snapshot_fixture


class SourceSnapshotLimit(unittest.TestCase):
    def setUp(self):
        self.root, profile = fixture(self)
        self.target = module("profiles").target_identity(
            profile["targets"]["production"]
        )

    def test_named_source_snapshot_is_validated_under_the_byte_limit(self):
        history = {
            "schema_version": 1,
            "type": "metadata-snapshot",
            "target": self.target,
            "fields": {},
            "images": {},
        }
        folder = snapshot_fixture(self.root / "state", history, {"a.txt": b"public"})
        record = json.loads((self.root / "metadata/listing.json").read_text())
        record["source_snapshot"] = (
            (folder / "manifest.json").relative_to(self.root).as_posix()
        )
        snapshots = module("snapshots")
        with patch.object(
            snapshots, "validate_snapshot", wraps=snapshots.validate_snapshot
        ) as validate:
            module("metadata").resolve_changelogs(self.root, record, self.target, {})
        limits = {call.kwargs.get("total_limit") for call in validate.call_args_list}
        self.assertEqual(limits, {module("records").FILE_LIMIT})


if __name__ == "__main__":
    unittest.main()
