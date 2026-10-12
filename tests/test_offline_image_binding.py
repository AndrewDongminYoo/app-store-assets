"""Bind semantic image validation to the exact inventoried input bytes."""

import contextlib
import hashlib
import struct
import tempfile
import unittest
import zlib
from pathlib import Path
from unittest.mock import patch

from app_store_assets import cli, decoding, records, snapshots


def png(width, height):
    def chunk(kind, data):
        return (
            struct.pack(">I", len(data))
            + kind
            + data
            + struct.pack(">I", zlib.crc32(kind + data))
        )

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress((b"\0" + b"\x20\x40\x60" * width) * height))
        + chunk(b"IEND", b"")
    )


def fixture(test):
    home = tempfile.TemporaryDirectory(prefix="bound-image-contract-")
    test.addCleanup(home.cleanup)
    root = Path(home.name).resolve()
    target = dict(
        store="google",
        platform="android",
        account="public",
        app_id="com.example.fixture",
        flavor="production",
        stage="production",
        version={"name": "1.0", "build": "9"},
        track="alpha",
    )
    original = png(512, 1024)
    record = dict(
        schema_version=1,
        type="metadata-snapshot",
        target=target,
        fields={},
        images={
            "en-US": {
                "phoneScreenshots": [
                    {
                        "file": "public.png",
                        "sha256": hashlib.sha256(original).hexdigest(),
                        "size": [1, 1],
                    }
                ]
            }
        },
    )
    manifest = dict(
        schema_version=1,
        type="snapshot",
        record=record,
        files={"public.png": hashlib.sha256(original).hexdigest()},
    )
    folder = root / records.record_digest(manifest)
    folder.mkdir()
    (folder / "public.png").write_bytes(original)
    (folder / "manifest.json").write_bytes(records.canonical(manifest))
    return root, folder, record, original


@contextlib.contextmanager
def swap_capture(image):
    original = image.read_bytes()
    capture = decoding.capture_bytes

    def interleaved(path, **kwargs):
        if Path(path) != image:
            return capture(path, **kwargs)
        image.write_bytes(png(1, 1))
        try:
            return capture(path, **kwargs)
        finally:
            image.write_bytes(original)

    with patch.object(decoding, "capture_bytes", side_effect=interleaved):
        yield


@contextlib.contextmanager
def swap_decoder_file():
    run = decoding.subprocess.run

    def interleaved(argv, **kwargs):
        if argv[0] != "magick" or not Path(argv[1]).is_file():
            return run(argv, **kwargs)
        image = Path(argv[1])
        original = image.read_bytes()
        image.write_bytes(png(1, 1))
        try:
            return run(argv, **kwargs)
        finally:
            image.write_bytes(original)

    with patch.object(decoding.subprocess, "run", side_effect=interleaved):
        yield


class ImageBindingTests(unittest.TestCase):
    def test_snapshot_rejects_dimension_capture_outside_inventory(self):
        _, folder, _, _ = fixture(self)
        with swap_capture(folder / "public.png"), self.assertRaises(ValueError):
            snapshots.validate_snapshot(folder)

    def test_diff_input_rejects_dimension_capture_outside_inventory(self):
        root, folder, record, _ = fixture(self)
        with swap_capture(folder / "public.png"), self.assertRaises(ValueError):
            cli.metadata_input(root, folder.name + "/manifest.json", record["target"])

    def test_decoder_consumes_captured_bytes_without_mutable_file_reopen(self):
        _, folder, _, _ = fixture(self)
        with swap_decoder_file():
            self.assertEqual(
                decoding.image_info(folder / "public.png")[:2], (512, 1024)
            )
