"""Path-backed non-image snapshot payloads are capped at the text limit."""

import unittest
from unittest.mock import patch

from offline_support import fixture, module


class PublisherTextLimit(unittest.TestCase):
    def setUp(self):
        self.root, profile = fixture(self)
        self.target = module("profiles").target_identity(
            profile["targets"]["production"]
        )

    def record(self, images=None):
        return {
            "schema_version": 1,
            "type": "metadata-snapshot",
            "target": self.target,
            "fields": {},
            "images": {"en-US": {"APP_IPHONE_67": images}} if images else {},
        }

    def test_path_backed_text_payload_is_capped_at_the_text_limit(self):
        publisher = module("publisher")
        source = self.root / "notes.txt"
        source.write_text("Public notes")
        state = self.root / "state"
        state.mkdir()
        limits = []

        def capture(path, *, limit):
            limits.append(limit)
            return original(path, limit=limit)

        original = publisher.capture_bytes
        with patch.object(publisher, "capture_bytes", capture):
            publisher.publish_snapshot(state, self.record(), {"notes.txt": source})
        self.assertEqual(limits, [publisher.TEXT_LIMIT])

    def test_supplied_text_bytes_are_capped_at_the_text_limit(self):
        publisher = module("publisher")
        state = self.root / "state"
        state.mkdir()
        payload = b"x" * (publisher.TEXT_LIMIT + 1)
        with self.assertRaisesRegex(ValueError, "text"):
            publisher.publish_snapshot(state, self.record(), {"notes.txt": payload})
        self.assertEqual(list(state.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
