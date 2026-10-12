"""Reject parser amplification before allocating archive entries or pixels."""

import io
import struct
import unittest
import zipfile
from unittest.mock import patch

from app_store_assets import artifacts, decoding


def archive_bytes(count=1):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("AndroidManifest.xml", b"public fixture")
        for index in range(count - 1):
            archive.writestr(str(index), b"")
    return stream.getvalue()


class ParserResourceBounds(unittest.TestCase):
    def test_entry_overflow_prevents_zipfile_construction(self):
        data = archive_bytes(3)
        with patch.object(artifacts, "ENTRY_LIMIT", 2, create=True):
            with patch.object(artifacts.zipfile, "ZipFile") as constructor:
                with self.assertRaisesRegex(ValueError, "bound|oversized"):
                    artifacts._container_kind(io.BytesIO(data))
            constructor.assert_not_called()

    def test_forged_small_entry_count_cannot_bypass_preflight(self):
        data = bytearray(archive_bytes(3))
        end = data.rfind(b"PK\x05\x06")
        struct.pack_into("<HH", data, end + 8, 1, 1)
        with patch.object(artifacts, "ENTRY_LIMIT", 2, create=True):
            with patch.object(artifacts.zipfile, "ZipFile") as constructor:
                with self.assertRaisesRegex(ValueError, "bound|oversized|count"):
                    artifacts._container_kind(io.BytesIO(data))
            constructor.assert_not_called()

    def test_central_directory_byte_overflow_prevents_zipfile_construction(self):
        data = archive_bytes()
        with patch.object(artifacts, "DIRECTORY_LIMIT", 8, create=True):
            with patch.object(artifacts.zipfile, "ZipFile") as constructor:
                with self.assertRaisesRegex(ValueError, "bound|oversized"):
                    artifacts._container_kind(io.BytesIO(data))
            constructor.assert_not_called()

    def test_prefixed_container_and_archive_comment_remain_supported(self):
        stream = io.BytesIO(b"public prefix" + archive_bytes())
        with zipfile.ZipFile(stream, "a") as archive:
            archive.comment = b"public comment"
        stream.seek(0)
        self.assertEqual(artifacts._container_kind(stream), "apk")

    def test_zip64_end_records_and_prefix_remain_supported(self):
        data = archive_bytes()
        end = data.rfind(b"PK\x05\x06")
        classic = struct.unpack(zipfile.structEndArchive, data[end:])
        zip64 = struct.pack(
            zipfile.structEndArchive64,
            zipfile.stringEndArchive64,
            44,
            45,
            45,
            0,
            0,
            1,
            1,
            classic[5],
            classic[6],
        )
        locator = struct.pack(
            zipfile.structEndArchive64Locator,
            zipfile.stringEndArchive64Locator,
            0,
            end,
            1,
        )
        for prefix in (b"", b"public prefix"):
            with self.subTest(prefix=prefix):
                self.assertEqual(
                    artifacts._container_kind(
                        io.BytesIO(prefix + data[:end] + zip64 + locator + data[end:])
                    ),
                    "apk",
                )

    def test_catalog_maximum_png_remains_decodable_with_resource_caps(self):
        import tempfile
        from pathlib import Path

        from test_offline_image_binding import png

        with tempfile.TemporaryDirectory() as home:
            image = Path(home).resolve() / "public.png"
            image.write_bytes(png(3840, 3840))
            self.assertEqual(decoding.image_info(image)[:2], (3840, 3840))

    def test_zip64_location_preflight_accepts_both_stdlib_record_locations(self):
        data = archive_bytes()
        end = data.rfind(b"PK\x05\x06")
        classic = list(struct.unpack(zipfile.structEndArchive, data[end:]))
        zip64 = struct.pack(
            zipfile.structEndArchive64,
            zipfile.stringEndArchive64,
            44,
            45,
            45,
            0,
            0,
            1,
            1,
            classic[5],
            classic[6],
        )
        locator = struct.pack(
            zipfile.structEndArchive64Locator,
            zipfile.stringEndArchive64Locator,
            0,
            end,
            1,
        )
        combined = data[:end] + zip64 + locator + data[end:]
        classic[0] = zipfile.stringEndArchive64
        for location in (end, end + len(zip64) + len(locator)):
            with (
                self.subTest(location=location),
                patch.object(
                    zipfile, "_EndRecData", return_value=classic + [b"", location]
                ),
            ):
                artifacts._preflight_directory(io.BytesIO(combined))

    def test_png_and_jpeg_dimensions_reject_before_native_decode(self):
        png = b"\x89PNG\r\n\x1a\n" + struct.pack(">I4sII", 13, b"IHDR", 100000, 100000)
        jpeg = (
            b"\xff\xd8\xff\xc0"
            + struct.pack(">HBHH", 11, 8, 65535, 65535)
            + b"\x01\x01\x11\x00"
        )
        for data, fmt in ((png, "PNG"), (jpeg, "JPEG")):
            with (
                self.subTest(format=fmt),
                patch.object(decoding.subprocess, "run") as run,
            ):
                with self.assertRaisesRegex(ValueError, "dimension|bound"):
                    decoding._decode(data, fmt, {"HOME": "/tmp"})
                run.assert_not_called()

    def test_decoder_receives_explicit_resource_limits(self):
        from test_offline_image_binding import png

        result = type(
            "Result",
            (),
            {"returncode": 0, "stderr": b"", "stdout": b"512|1024|srgb|PNG\n"},
        )()
        with patch.object(decoding.subprocess, "run", return_value=result) as run:
            self.assertEqual(
                decoding._decode(png(512, 1024), "PNG", {"HOME": "/tmp"}),
                (512, 1024, False),
            )
        argv = run.call_args[0][0]
        for resource in (
            "memory",
            "map",
            "disk",
            "width",
            "height",
            "area",
            "thread",
            "time",
            "list-length",
        ):
            self.assertIn(
                ["-limit", resource], [argv[i : i + 2] for i in range(len(argv) - 1)]
            )
