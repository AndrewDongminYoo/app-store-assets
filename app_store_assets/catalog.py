"""Frozen supported store slots; decoded bytes, not extensions or assumptions."""

import collections
import hashlib
import os
import tempfile
from pathlib import Path

from .decoding import image_info
from .environment import local_environment
from .metadata import normalize_fields
from .records import file_digest, read_json, safe_path

CATALOG_FILE = Path(__file__).resolve().parents[1] / "catalog/store-rules-v1.json"


def rules():
    return read_json(CATALOG_FILE)


def slot_rule(store, slot):
    try:
        return rules()["stores"][store]["slots"][slot]
    except KeyError:
        raise ValueError(f"unsupported store image slot: {store}/{slot}") from None


def encoded_format(path):
    path = Path(path)
    if path.name.startswith("."):
        raise ValueError("hidden image would be omitted by the reader")
    with path.open("rb") as stream:
        header = stream.read(26)
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        fmt, extensions = "PNG", {".png", ".PNG"}
    elif header.startswith(b"\xff\xd8\xff"):
        fmt, extensions = "JPEG", {".jpg", ".JPG", ".jpeg", ".JPEG"}
    else:
        raise ValueError(
            "image format signature is not PNG/JPEG; no delegate will be invoked"
        )
    if path.suffix not in extensions:
        raise ValueError("image format/extension differs from the Fastlane reader")
    return fmt, header


def validate_images(root, entries, store):
    result = []
    seen = set()
    counts = collections.Counter()
    for entry in entries:
        path = safe_path(root, entry["file"])
        if entry["file"] in seen:
            raise ValueError("duplicate image inventory entry")
        seen.add(entry["file"])
        normalize_fields({entry["locale"]: {}})
        rule = slot_rule(store, entry["slot"])
        expected = file_digest(path)
        if path.stat().st_size > 64 * 1024 * 1024:
            raise ValueError("image exceeds bounded local decoder input")
        with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW), "rb") as stream:
            captured = stream.read(64 * 1024 * 1024 + 1)
        if (
            len(captured) > 64 * 1024 * 1024
            or hashlib.sha256(captured).hexdigest() != expected
        ):
            raise ValueError("image changed while capturing bytes")
        with tempfile.TemporaryDirectory(prefix="image-reader-home-") as home:
            staged = Path(home) / path.name
            staged.write_bytes(captured)
            fmt, header = encoded_format(staged)
            width, height, alpha = image_info(staged, env=local_environment(home))
        if fmt not in rule["formats"]:
            raise ValueError("image format is unsupported for slot")
        if rule["alpha"] == "forbidden" and alpha:
            raise ValueError("alpha channel is forbidden for slot")
        if rule["alpha"] == "required-rgba32" and (
            fmt != "PNG" or len(header) < 26 or header[24:26] != bytes([8, 6])
        ):
            raise ValueError("icon requires a 32-bit RGBA PNG")
        if "sizes" in rule:
            accepted = rule["sizes"] + (
                [size[::-1] for size in rule["sizes"]] if rule.get("rotate") else []
            )
            if [width, height] not in accepted:
                raise ValueError("image dimensions do not match slot")
        elif (
            min(width, height) < rule["min_dimension"]
            or max(width, height) > rule["max_dimension"]
        ):
            raise ValueError("image dimensions exceed slot limits")
        elif max(width, height) / min(width, height) > rule["max_aspect"]:
            raise ValueError("image aspect ratio exceeds slot limit")
        if len(captured) > rule.get("max_bytes", float("inf")):
            raise ValueError("image file size exceeds slot limit")
        digest = expected
        if file_digest(path) != digest:
            raise ValueError("image changed during validation")
        if entry.get("sha256", digest) != digest:
            raise ValueError("listing image hash differs")
        counts[entry["locale"], entry["slot"]] += 1
        if counts[entry["locale"], entry["slot"]] > rule["max_count"]:
            raise ValueError("too many images in one locale/slot")
        result.append(dict(entry, size=[width, height], sha256=digest))
    return result


def validate_fields(fields, store, proposed=True):
    clean = normalize_fields(fields)
    if store == "google":
        for values in clean.values():
            if "description" in values:
                if (
                    "full_description" in values
                    and values["full_description"] != values["description"]
                ):
                    raise ValueError("conflicting Google description alias")
                values["full_description"] = values.pop("description")
    store_rules = rules()["stores"].get(store, {})
    limits = store_rules.get("text_limits", {})
    for values in clean.values():
        if store in ("apple", "google") and set(values) - set(
            store_rules["supported_fields"]
        ):
            raise ValueError(f"unsupported {store} metadata field")
        for key, value in values.items():
            if (
                proposed
                and store == "apple"
                and key in ("support_url", "privacy_url")
                and not value
            ):
                raise ValueError("required Apple URL cannot be cleared")
            if key in limits:
                limit, unit = limits[key]
                length = (
                    len(value.encode("utf-8")) if unit == "utf8-bytes" else len(value)
                )
                if proposed and length < store_rules.get("text_minimums", {}).get(
                    key, 0
                ):
                    raise ValueError(f"metadata field minimum not met: {key}")
                if length > limit:
                    raise ValueError(f"metadata field limit exceeded: {key}")
    return clean


def validate_apple_localizations(listing, remote, operation):
    """Reject unavailable selected-version/AppInfo fields before store effects."""
    if not isinstance(remote.get("version_id"), str) or not remote["version_id"]:
        raise ValueError("exact selected Apple version ID required")
    if remote.get("editable") is not True or remote.get("review_active") is not False:
        raise ValueError(
            "selected Apple version must be editable with no active review"
        )
    version_fields = {
        "description",
        "keywords",
        "promotional_text",
        "release_notes",
        "support_url",
        "marketing_url",
    }
    info_fields = {"name", "subtitle", "privacy_url"}
    requested = (
        listing.get("fields", {})
        if operation == "metadata"
        else listing.get("images", {})
    )
    for locale, values in requested.items():
        existing = remote.get("fields", {}).get(locale, {})
        # Native snapshots include every version field, even when its text is empty.
        if not version_fields.intersection(existing):
            raise ValueError(f"Apple version locale is unavailable: {locale}")
        if operation == "metadata" and info_fields.intersection(values):
            if not remote.get("app_info_id"):
                raise ValueError("exact editable app-info snapshot required")
            if not info_fields.intersection(values).issubset(existing):
                raise ValueError(f"Apple app-info locale is unavailable: {locale}")


def submission_readiness(store, slots, supports_ipad=False):
    required = rules()["stores"][store]["submission_required"]
    if store == "apple":
        selected = [required["iphone"]] + ([required["ipad"]] if supports_ipad else [])
        missing = sorted(set(selected) - set(slots))
        return {
            "ready": not missing,
            "missing": missing,
            "scope": "required-image-classes-only",
        }
    return {
        "ready": False,
        "missing": ["verify-total-screenshot-count"],
        "scope": "listing-not-release-approval",
    }
