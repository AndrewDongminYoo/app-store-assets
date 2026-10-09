"""Existing still-image decoder isolated from the legacy preparation CLI."""

import subprocess

FORMAT_EXTENSIONS = {
    "PNG": {".png", ".PNG"},
    "JPEG": {".jpg", ".JPG", ".jpeg", ".JPEG"},
}


def image_info(file, env=None):
    if file.name.startswith("."):
        raise ValueError(f"hidden screenshot would be skipped by Fastlane: {file}")
    if file.suffix not in set().union(*FORMAT_EXTENSIONS.values()):
        raise ValueError(f"unsupported Fastlane image extension: {file}")
    # Decode the pixel stream, not just the IHDR header. Warnings also reject
    # truncated images that ImageMagick might otherwise recover.
    result = subprocess.run(
        [
            "magick",
            str(file),
            "-regard-warnings",
            "-format",
            "%w|%h|%[channels]|%m\n",
            "info:",
        ],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode or result.stderr:
        raise ValueError(f"cannot decode image: {file}")
    values = result.stdout.strip().split("|")
    if len(values) != 4 or "\n" in result.stdout.strip():
        raise ValueError(f"expected one still image: {file}")
    if file.suffix not in FORMAT_EXTENSIONS.get(values[3], set()):
        raise ValueError(f"image format does not match extension: {file}")
    width, height = map(int, values[:2])
    header = file.read_bytes()[:26]
    alpha = values[2].split()[0].lower().endswith("a")
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        # Fully opaque RGBA still has an alpha channel. Palette transparency
        # is detected by the decoder above.
        alpha = alpha or header[25] in (4, 6)
    return width, height, alpha
