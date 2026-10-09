"""Existing still-image decoder isolated from the legacy preparation CLI."""

import hashlib
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


def image_bytes(file, *, expected_sha256=None):
    if expected_sha256 is not None:
        digest(expected_sha256)
    file = Path(file)
    data = capture_bytes(file, limit=IMAGE_LIMIT)
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
    data, fmt = image_bytes(file, expected_sha256=expected_sha256)
    with tempfile.TemporaryDirectory(prefix="offline-decode-") as home:
        return _decode(data, fmt, local_environment(home))


def _decode(data, fmt, env):
    # Decode the pixel stream, not just the IHDR header. Warnings also reject
    # truncated images that ImageMagick might otherwise recover.
    result = subprocess.run(
        [
            "magick",
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
    alpha = values[2].split()[0].lower().endswith("a")
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        # Fully opaque RGBA still has an alpha channel. Palette transparency
        # is detected by the decoder above.
        alpha = alpha or (len(data) >= 26 and data[25] in (4, 6))
    return width, height, alpha
