"""Existing still-image decoder isolated from the legacy preparation CLI."""

import hashlib
import struct
import subprocess
import tempfile
from pathlib import Path

from .contracts import digest
from .environment import local_environment
from .records import capture_bytes

FORMAT_EXTENSIONS = {
    "PNG": {".png", ".PNG"},
    "JPEG": {".jpg", ".JPG", ".jpeg", ".JPEG"},
}
IMAGE_LIMIT = 64 * 1024 * 1024
DIMENSION_LIMIT = 4096
PIXEL_LIMIT = DIMENSION_LIMIT * DIMENSION_LIMIT


def _dimensions(data, fmt):
    if fmt == "PNG":
        if len(data) < 24 or data[8:16] != b"\0\0\0\rIHDR":
            raise ValueError("cannot decode PNG dimensions")
        width, height = struct.unpack(">II", data[16:24])
    else:
        width = height = None
        position = 2
        while position < len(data):
            if data[position] != 0xFF:
                raise ValueError("cannot decode JPEG dimensions")
            while position < len(data) and data[position] == 0xFF:
                position += 1
            if position >= len(data):
                break
            marker = data[position]
            position += 1
            if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
                continue
            if marker in (0x00, 0xD9, 0xDA) or position + 2 > len(data):
                break
            size = int.from_bytes(data[position : position + 2], "big")
            if size < 2 or position + size > len(data):
                break
            if marker in (
                0xC0,
                0xC1,
                0xC2,
                0xC3,
                0xC5,
                0xC6,
                0xC7,
                0xC9,
                0xCA,
                0xCB,
                0xCD,
                0xCE,
                0xCF,
            ):
                if size < 8:
                    break
                height, width = struct.unpack(">HH", data[position + 3 : position + 7])
                break
            position += size
        else:
            raise ValueError("cannot decode JPEG dimensions")
        if width is None:
            raise ValueError("cannot decode JPEG dimensions")
    if (
        not (0 < width <= DIMENSION_LIMIT and 0 < height <= DIMENSION_LIMIT)
        or width * height > PIXEL_LIMIT
    ):
        raise ValueError("image dimensions exceed decoder resource bound")
    return width, height


def image_bytes(file, *, expected_sha256=None):
    if expected_sha256 is not None:
        digest(expected_sha256)
    data = capture_bytes(file, limit=IMAGE_LIMIT)
    file = Path(file)
    if (
        expected_sha256 is not None
        and hashlib.sha256(data).hexdigest() != expected_sha256
    ):
        raise ValueError("decoded image capture differs from bound hash")
    fmt = (
        "PNG"
        if data.startswith(b"\x89PNG\r\n\x1a\n")
        else "JPEG"
        if data.startswith(b"\xff\xd8\xff")
        else None
    )
    if file.suffix not in FORMAT_EXTENSIONS.get(fmt, set()) or file.name.startswith(
        "."
    ):
        raise ValueError("unsupported image signature/name/extension")
    return data, fmt


def image_info(file, env=None, *, expected_sha256=None):
    """Decode in a fresh isolated environment; env is compatibility-only."""
    data, fmt = image_bytes(file, expected_sha256=expected_sha256)
    with tempfile.TemporaryDirectory(prefix="offline-decode-") as home:
        return _decode(data, fmt, local_environment(home))


def _decode(data, fmt, env):
    dimensions = _dimensions(data, fmt)
    # Decode the pixel stream, not just the IHDR header. Warnings also reject
    # truncated images that ImageMagick might otherwise recover.
    result = subprocess.run(
        [
            "magick",
            "-limit",
            "memory",
            "512MiB",
            "-limit",
            "map",
            "0",
            "-limit",
            "disk",
            "0",
            "-limit",
            "width",
            str(DIMENSION_LIMIT),
            "-limit",
            "height",
            str(DIMENSION_LIMIT),
            "-limit",
            "area",
            str(PIXEL_LIMIT),
            "-limit",
            "thread",
            "1",
            "-limit",
            "time",
            "30",
            "-limit",
            "list-length",
            "2",
            {"PNG": "png:-", "JPEG": "jpeg:-"}[fmt],
            "-regard-warnings",
            "-format",
            "%w|%h|%[channels]|%m\n",
            "info:",
        ],
        input=data,
        env={**env, "MAGICK_TEMPORARY_PATH": env["HOME"]},
        capture_output=True,
        timeout=60,
        check=False,
    )
    if result.returncode or result.stderr:
        raise ValueError("cannot decode bound image bytes")
    output = result.stdout.decode("ascii").strip()
    values = output.split("|")
    if len(values) != 4 or "\n" in output:
        raise ValueError("expected one still image")
    if values[3] != fmt:
        raise ValueError("decoded format differs from captured signature")
    width, height = map(int, values[:2])
    if (width, height) != dimensions:
        raise ValueError("decoded dimensions differ from bounded header")
    alpha = values[2].split()[0].lower().endswith("a")
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        # Fully opaque RGBA still has an alpha channel. Palette transparency
        # is detected by the decoder above.
        alpha = alpha or (len(data) >= 26 and data[25] in (4, 6))
    return width, height, alpha
