"""Aggregate reservations precede reads for every mixed source ordering."""

import hashlib
import itertools
import unittest
from unittest.mock import patch

import app_store_assets_local.publisher as publisher
import test_offline_image_binding as images
from offline_support import fixture, module


class SuppliedCaptureBudget(unittest.TestCase):
    def metadata(self):
        root, profile = fixture(self)
        target = module("profiles").target_identity(profile["targets"]["production"])
        return root, {
            "schema_version": 1,
            "type": "metadata",
            "target": target,
            "fields": {},
            "images": {},
        }

    def observe(self, root, record, entries, total, image_limit=None):
        observations = []
        original = publisher.capture_bytes

        def captured(path, *, limit):
            observations.append(limit)
            return original(path, limit=limit)

        output = root / "history"
        with (
            patch.object(publisher, "FILE_LIMIT", total),
            patch.object(publisher, "capture_bytes", side_effect=captured),
        ):
            if image_limit is None:
                publisher.publish_snapshot(output, record, dict(entries))
            else:
                with patch.object(publisher, "IMAGE_LIMIT", image_limit):
                    publisher.publish_snapshot(output, record, dict(entries))
        return output, observations

    def test_all_orderings_reserve_every_supplied_byte_before_path_capture(self):
        root, record = self.metadata()
        path = root / "path.txt"
        path.write_bytes(b"p" * 8)
        entries = [("path.txt", path), ("one.txt", b"a" * 7), ("two.txt", b"b" * 8)]
        for index, ordering in enumerate(itertools.permutations(entries)):
            with self.subTest(order=index):
                observed = []
                original = publisher.capture_bytes

                def captured(path, *, limit):
                    observed.append(limit)
                    return original(path, limit=limit)

                with (
                    patch.object(publisher, "FILE_LIMIT", 16),
                    patch.object(publisher, "capture_bytes", side_effect=captured),
                ):
                    with self.assertRaisesRegex(ValueError, "bound|limit"):
                        publisher.publish_snapshot(
                            root / "history", record, dict(ordering)
                        )
                self.assertEqual(observed, [1])
                self.assertFalse((root / "history").exists())

    def test_supplied_total_overflow_prevents_every_path_read(self):
        root, record = self.metadata()
        path = root / "path.txt"
        path.write_bytes(b"p")
        entries = [("path.txt", path), ("one.txt", b"a" * 8), ("two.txt", b"b" * 9)]
        for index, ordering in enumerate(itertools.permutations(entries)):
            with self.subTest(order=index):
                with (
                    patch.object(publisher, "FILE_LIMIT", 16),
                    patch.object(publisher, "capture_bytes") as captured,
                ):
                    with self.assertRaisesRegex(ValueError, "bound|limit"):
                        publisher.publish_snapshot(
                            root / "history", record, dict(ordering)
                        )
                captured.assert_not_called()
                self.assertFalse((root / "history").exists())

    def test_exact_aggregate_bound_publishes_for_both_source_orders(self):
        for path_first in (True, False):
            with self.subTest(path_first=path_first):
                root, record = self.metadata()
                path = root / "path.txt"
                path.write_bytes(b"p" * 8)
                entries = [("path.txt", path), ("supplied.txt", b"s" * 8)]
                if not path_first:
                    entries.reverse()
                output, observed = self.observe(root, record, entries, 16)
                self.assertEqual(observed, [8])
                snapshot = next(output.iterdir())
                self.assertEqual(
                    module("snapshots").validate_snapshot(snapshot)["files"][
                        "path.txt"
                    ],
                    hashlib.sha256(b"p" * 8).hexdigest(),
                )

    def test_oversized_supplied_image_prevents_unrelated_path_capture(self):
        for path_first in (True, False):
            with self.subTest(path_first=path_first):
                root, _, record, _ = images.fixture(self)
                path = root / "extra.txt"
                path.write_bytes(b"p")
                entries = [("extra.txt", path), ("public.png", b"i" * 9)]
                if not path_first:
                    entries.reverse()
                with (
                    patch.object(publisher, "FILE_LIMIT", 16),
                    patch.object(publisher, "IMAGE_LIMIT", 8),
                    patch.object(publisher, "capture_bytes") as captured,
                ):
                    with self.assertRaisesRegex(ValueError, "bound|limit"):
                        publisher.publish_snapshot(
                            root / "new-history", record, dict(entries)
                        )
                captured.assert_not_called()
                self.assertFalse((root / "new-history").exists())

    def test_exact_supplied_image_and_total_bounds_preserve_path_remainder(self):
        root, folder, record, _ = images.fixture(self)
        data = (folder / "public.png").read_bytes()
        record["images"]["en-US"]["phoneScreenshots"][0]["size"] = [512, 1024]
        path = root / "extra.txt"
        path.write_bytes(b"p")
        output, observed = self.observe(
            root,
            record,
            [("extra.txt", path), ("public.png", data)],
            len(data) + 1,
            len(data),
        )
        self.assertEqual(observed, [1])
        module("snapshots").validate_snapshot(next(output.iterdir()))
