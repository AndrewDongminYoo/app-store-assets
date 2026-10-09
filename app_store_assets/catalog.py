"""Frozen supported store slots; decoded bytes, not extensions or assumptions."""

import collections
import re
import tempfile
from pathlib import Path

from .contracts import exact_keys, image_entry, public_text, public_url
from .decoding import image_info
from .environment import local_environment
from .metadata import normalize_fields
from .records import capture_bytes, file_digest, open_read, read_json, safe_path

CATALOG_FILE = Path(__file__).resolve().parents[1] / "catalog/store-rules-v1.json"


def validate_catalog(value):
    keys = {
        "schema_version",
        "catalog_version",
        "checked_on",
        "fastlane_reader",
        "sources",
        "stores",
    }
    exact_keys(value, keys, keys)
    if type(value["schema_version"]) is not int or value["schema_version"] != 1:
        raise ValueError("unsupported catalog schema")
    for key in ("catalog_version", "checked_on", "fastlane_reader"):
        public_text(value[key], "catalog " + key)
    source_keys = {
        "apple_images",
        "apple_text",
        "apple_name",
        "google_images",
        "google_release_notes",
        "google_text",
    }
    exact_keys(value["sources"], source_keys, source_keys)
    for url in value["sources"].values():
        public_url(url)
    exact_keys(value["stores"], {"apple", "google"}, {"apple", "google"})

    def positive(number):
        if type(number) is not int or number <= 0:
            raise ValueError("invalid catalog positive integer")

    for store, data in value["stores"].items():
        required = {"slots", "supported_fields", "text_limits", "submission_required"}
        exact_keys(data, required | {"text_minimums", "release_notes_limit"}, required)
        if not isinstance(data["slots"], dict) or not data["slots"]:
            raise ValueError("invalid catalog slots")
        for name, rule in data["slots"].items():
            if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", name):
                raise ValueError("invalid catalog slot")
            base = {"alpha", "formats", "max_count"}
            exact_keys(
                rule,
                base
                | {
                    "sizes",
                    "rotate",
                    "min_dimension",
                    "max_dimension",
                    "max_aspect",
                    "max_bytes",
                },
                base,
            )
            if rule["alpha"] not in ("forbidden", "required-rgba32"):
                raise ValueError("invalid alpha rule")
            if (
                not isinstance(rule["formats"], list)
                or not rule["formats"]
                or any(v not in ("PNG", "JPEG") for v in rule["formats"])
            ):
                raise ValueError("invalid catalog formats")
            positive(rule["max_count"])
            if "sizes" in rule:
                if (
                    not isinstance(rule["sizes"], list)
                    or not rule["sizes"]
                    or type(rule.get("rotate")) is not bool
                ):
                    raise ValueError("invalid catalog sizes")
                if set(rule) & {"min_dimension", "max_dimension", "max_aspect"}:
                    raise ValueError("ambiguous slot dimensions")
                for size in rule["sizes"]:
                    if not isinstance(size, list) or len(size) != 2:
                        raise ValueError("invalid catalog size")
                    for number in size:
                        positive(number)
            else:
                if (
                    not {"min_dimension", "max_dimension", "max_aspect"} <= set(rule)
                    or "rotate" in rule
                ):
                    raise ValueError("missing bounded slot dimensions")
                positive(rule["min_dimension"])
                positive(rule["max_dimension"])
                if (
                    rule["max_dimension"] < rule["min_dimension"]
                    or type(rule["max_aspect"]) not in (int, float)
                    or not 1 <= rule["max_aspect"] < float("inf")
                ):
                    raise ValueError("invalid catalog dimension/aspect range")
            if "max_bytes" in rule:
                positive(rule["max_bytes"])
        fields = data["supported_fields"]
        from .metadata import PUBLIC_FIELDS

        if (
            not isinstance(fields, list)
            or not fields
            or any(not isinstance(v, str) or v not in PUBLIC_FIELDS for v in fields)
            or len(set(fields)) != len(fields)
        ):
            raise ValueError("invalid catalog supported fields")
        exact_keys(data["text_limits"], fields)
        for pair in data["text_limits"].values():
            if (
                not isinstance(pair, list)
                or len(pair) != 2
                or pair[1] not in ("characters", "utf8-bytes")
            ):
                raise ValueError("invalid catalog text limit")
            positive(pair[0])
        exact_keys(data.get("text_minimums", {}), data["text_limits"])
        for key, number in data.get("text_minimums", {}).items():
            positive(number)
            if number > data["text_limits"][key][0]:
                raise ValueError("invalid catalog minimum")
        required_keys = (
            {"iphone", "ipad"}
            if store == "apple"
            else {"minimum_screenshots_across_devices"}
        )
        exact_keys(data["submission_required"], required_keys, required_keys)
        for item in data["submission_required"].values():
            if store == "apple":
                if not isinstance(item, str) or item not in data["slots"]:
                    raise ValueError("invalid required catalog slot")
            else:
                positive(item)
        if store == "google":
            positive(data.get("release_notes_limit"))
        elif "release_notes_limit" in data:
            raise ValueError("unexpected Apple notes rule")
    return value


def rules():
    return validate_catalog(read_json(CATALOG_FILE))


def slot_rule(store, slot):
    try:
        return rules()["stores"][store]["slots"][slot]
    except KeyError:
        raise ValueError(f"unsupported store image slot: {store}/{slot}") from None


def encoded_format(path):
    path = Path(path)
    if path.name.startswith("."):
        raise ValueError("hidden image would be omitted by the reader")
    with open_read(path) as stream:
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
    if store not in ("apple", "google") or not isinstance(entries, list):
        raise ValueError("unsupported image store/inventory")
    for entry in entries:
        image_entry(entry, grouped=True, required_file=True)
        path = safe_path(root, entry["file"])
        if entry["file"] in seen:
            raise ValueError("duplicate image inventory entry")
        seen.add(entry["file"])
        normalize_fields({entry["locale"]: {}})
        rule = slot_rule(store, entry["slot"])
        expected = file_digest(path)
        captured = capture_bytes(path, limit=64 * 1024 * 1024)
        import hashlib

        if hashlib.sha256(captured).hexdigest() != expected:
            raise ValueError("image changed while capturing bytes")
        with tempfile.TemporaryDirectory(prefix="image-reader-home-") as home:
            staged = Path(home).resolve() / path.name
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
    if store not in ("apple", "google"):
        raise ValueError("unsupported metadata store")
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
