"""Existing snapshot winners are validated under the aggregate byte bound."""

import unittest
from unittest.mock import patch

from offline_support import fixture, module


class SnapshotWinnerBound(unittest.TestCase):
    def test_existing_snapshot_winner_validation_is_bounded(self):
        root, profile = fixture(self)
        target = module("profiles").target_identity(profile["targets"]["production"])
        publisher = module("publisher")
        original = publisher.validate_snapshot
        limits = []

        def check(*args, **kwargs):
            limits.append(kwargs.get("total_limit"))
            return original(*args, **kwargs)

        record = {
            "schema_version": 1,
            "type": "metadata-snapshot",
            "target": target,
            "fields": {},
            "images": {},
        }
        state = root / "state"
        state.mkdir()
        with patch.object(publisher, "validate_snapshot", side_effect=check):
            for _ in range(2):
                publisher.publish_snapshot(state, record, {"notes.txt": b"Public"})
        self.assertTrue(limits)
        self.assertEqual(set(limits), {publisher.FILE_LIMIT})


if __name__ == "__main__":
    unittest.main()
