"""The writer uses the reader's byte binding before durable publication."""

import unittest

import test_offline_image_binding as images

from app_store_assets_local.metadata_io import export_metadata
from app_store_assets_local.publisher import publish_snapshot


class LocalImageBindingTests(unittest.TestCase):
    def test_export_rejects_wrong_dimension_capture_before_output(self):
        root, folder, record, _ = images.fixture(self)
        for dry_run in (True, False):
            with self.subTest(dry_run=dry_run):
                destination = root / ("editing-" + str(dry_run))
                with (
                    images.swap_capture(folder / "public.png"),
                    self.assertRaises(ValueError),
                ):
                    export_metadata(
                        root, folder, record["target"], destination, dry_run=dry_run
                    )
                self.assertFalse(destination.exists())

    def test_publisher_decodes_supplied_bytes_before_history_creation(self):
        root, _, record, original = images.fixture(self)
        history = root / "new-history"
        with images.swap_decoder_file(), self.assertRaises(ValueError):
            publish_snapshot(history, record, {"public.png": original})
        self.assertFalse(history.exists())
