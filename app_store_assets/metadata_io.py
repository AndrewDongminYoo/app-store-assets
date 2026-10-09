"""Explicit public listing export/import; never overwrite an editing tree."""

import hashlib
import os
import re
import tempfile
from pathlib import Path

from .catalog import CATALOG_FILE, encoded_format, validate_fields, validate_images
from .identity import runtime_inventory
from .metadata import IMAGE_FIELDS, normalize_fields, validate_public_metadata
from .records import (
    canonical,
    file_digest,
    inventory,
    read_json,
    record_digest,
    safe_path,
    verify_inventory,
)
from .snapshots import publish_snapshot, reject_snapshot_write, validate_snapshot

FIELDS = {
    "apple": {
        "name",
        "subtitle",
        "description",
        "keywords",
        "promotional_text",
        "release_notes",
        "support_url",
        "marketing_url",
        "privacy_url",
    },
    "google": {"title", "short_description", "full_description", "video"},
}
APPLE_FOLDERS = {
    "APP_IPHONE_65": "iphone65",
    "APP_IPHONE_67": "iphone67",
    "APP_IPHONE_61": "iphone61",
    "APP_IPAD_PRO_129": "ipad129",
    "APP_IPAD_PRO_3GEN_129": "ipad3gen129",
}
EXPORT_MANIFEST = "store-assets-export.json"


def confined(root, path):
    lexical_root = Path(os.path.abspath(root))
    canonical_root = lexical_root.resolve()
    path = Path(path)
    if not path.is_absolute():
        return safe_path(canonical_root, path.as_posix())
    # Accept the caller's root alias (/var on macOS) and its resolved spelling,
    # while still checking every input component for symlinks before reading it.
    for base in (lexical_root, canonical_root):
        if path.is_relative_to(base):
            return safe_path(canonical_root, path.relative_to(base).as_posix())
    raise ValueError("metadata path must stay inside the project")


def text_bytes(path):
    if path.stat().st_size > 8 * 1024 * 1024:
        raise ValueError("public metadata text exceeds bound")
    return path.read_bytes()


def export_metadata(root, snapshot, target, destination, dry_run=False):
    snapshot, destination = confined(root, snapshot), confined(root, destination)
    root = Path(root).resolve()
    reject_snapshot_write(destination)
    if destination.is_relative_to(snapshot):
        raise ValueError("export destination overlaps immutable source snapshot")
    if destination.exists():
        raise ValueError("export destination exists; never overwrite an editing tree")
    manifest = validate_snapshot(snapshot)
    record = validate_public_metadata(manifest["record"], target)
    if record.get("type") != "metadata-snapshot" or record.get("target") != target:
        raise ValueError("export snapshot target/type differs")
    fields = validate_fields(record.get("fields", {}), target["store"], proposed=False)
    maps = {"fields": [], "images": [], "notes": []}
    files = {}
    for locale, values in fields.items():
        for key, value in values.items():
            if key not in FIELDS[target["store"]]:
                raise ValueError("unsupported repository metadata field")
            name = locale + "/" + key + ".txt"
            files[name] = value.encode("utf-8")
            maps["fields"].append({"locale": locale, "key": key, "file": name})
    for locale, groups in record.get("images", {}).items():
        normalize_fields({locale: {}})
        for slot, images in groups.items():
            if not re.fullmatch("[A-Za-z0-9_-]+", slot):
                raise ValueError("unsupported image group path")
            folder = (
                APPLE_FOLDERS.get(slot, slot) if target["store"] == "apple" else slot
            )
            for index, image in enumerate(images):
                source = safe_path(snapshot, image["file"])
                if image.get("sha256") != manifest["files"].get(image["file"]):
                    raise ValueError("download image annotation/hash differs")
                fmt, _ = encoded_format(source)
                name = f"{locale}/images/{folder}/{index + 1:02}." + (
                    "png" if fmt == "PNG" else "jpg"
                )
                data = source.read_bytes()
                if hashlib.sha256(data).hexdigest() != image["sha256"]:
                    raise ValueError("download bytes changed during export")
                files[name] = data
                maps["images"].append(
                    {
                        "locale": locale,
                        "slot": slot,
                        "file": name,
                        "remote": {
                            k: v
                            for k, v in image.items()
                            if k in IMAGE_FIELDS - {"file", "sha256"}
                        },
                    }
                )
    notes = {}
    if target["store"] == "google":
        matches = [
            r
            for r in record.get("releases", [])
            if target["version"]["build"] in r.get("version_codes", [])
        ]
        if len(matches) > 1:
            raise ValueError("ambiguous selected track changelog")
        notes = matches[0].get("notes", {}) if matches else {}
    for locale, text in notes.items():
        normalize_fields({locale: {"release_notes": text}})
        name = locale + "/changelogs/" + target["version"]["build"] + ".txt"
        files[name] = text.encode("utf-8")
        maps["notes"].append({"locale": locale, "file": name})
    value = {
        "schema_version": 1,
        "type": "metadata-export",
        "target": target,
        "source_snapshot": record_digest(manifest),
        "format": "fastlane-repository-v1",
        **maps,
    }
    if dry_run:
        return {"status": "dry-run", "target": target, "effects": []}
    # mkdir atomically reserves a new destination. A concurrent/existing editor wins.
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.mkdir()
    for name, data in files.items():
        path = safe_path(destination, name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    (destination / EXPORT_MANIFEST).write_bytes(canonical(value))
    return destination


def import_metadata(
    root, source, target, output, state, metadata_only=False, dry_run=False
):
    source, output, state = (confined(root, p) for p in (source, output, state))
    root = Path(root).resolve()
    reject_snapshot_write(output)
    reject_snapshot_write(state)
    if output.exists():
        raise ValueError("import output exists; never overwrite an editing tree")
    if output.is_relative_to(source) or state.is_relative_to(source):
        raise ValueError("import output/history overlaps the editing tree")
    manifest_path = safe_path(source, EXPORT_MANIFEST)
    value = read_json(manifest_path)
    if (
        value.get("schema_version") != 1
        or value.get("type") != "metadata-export"
        or value.get("format") != "fastlane-repository-v1"
        or value.get("target") != target
    ):
        raise ValueError("import target/export format differs")
    # Validate the public format before hashing any manifest-directed input.
    for entry in value["fields"]:
        locale, key = entry["locale"], entry["key"]
        normalize_fields({locale: {}})
        if (
            key not in FIELDS[target["store"]]
            or entry["file"] != locale + "/" + key + ".txt"
        ):
            raise ValueError("unsupported public metadata field/path")
    for entry in value["notes"]:
        locale = entry["locale"]
        normalize_fields({locale: {}})
        if (
            target["store"] != "google"
            or entry["file"]
            != locale + "/changelogs/" + target["version"]["build"] + ".txt"
        ):
            raise ValueError("unsupported public changelog path")
    for entry in value["images"]:
        locale = entry["locale"]
        normalize_fields({locale: {}})
        if not re.fullmatch(
            re.escape(locale) + r"/images/[A-Za-z0-9_-]+/[0-9]{2,}\.(png|jpg)",
            entry["file"],
        ):
            raise ValueError("unsupported public image path")
    declared = {EXPORT_MANIFEST} | {
        entry["file"]
        for group in ("fields", "images", "notes")
        for entry in value[group]
    }
    expected = inventory(source, sorted(declared))
    verify_inventory(source, expected, exact=True)
    if read_json(manifest_path) != value:
        raise ValueError("export manifest changed during import")

    def captured_text(name):
        data = text_bytes(safe_path(source, name))
        if hashlib.sha256(data).hexdigest() != expected[name]:
            raise ValueError("metadata text changed outside the bound inventory")
        return data.decode("utf-8")

    expected_names = {EXPORT_MANIFEST}
    fields, images, notes, captured = {}, {}, {}, {}
    seen = set()
    for entry in value["fields"]:
        locale, key, name = entry["locale"], entry["key"], entry["file"]
        if key not in FIELDS[target["store"]] or (locale, key) in seen:
            raise ValueError("duplicate/unsupported public metadata field")
        if name != locale + "/" + key + ".txt":
            raise ValueError("metadata field path differs from repository format")
        seen.add((locale, key))
        expected_names.add(name)
        fields.setdefault(locale, {})[key] = captured_text(name)
    for entry in value["notes"]:
        locale, name = entry["locale"], entry["file"]
        if locale in notes or target["store"] != "google":
            raise ValueError("duplicate/unsupported changelog")
        expected_names.add(name)
        notes[locale] = captured_text(name)
        normalize_fields({locale: {"release_notes": notes[locale]}})
    for entry in value["images"]:
        name = entry["file"]
        safe_path(source, name)
        expected_names.add(name)
        if not metadata_only:
            remote = entry.get("remote", {})
            images.setdefault(entry["locale"], {}).setdefault(entry["slot"], []).append(
                {
                    k: v
                    for k, v in remote.items()
                    if k in IMAGE_FIELDS - {"file", "sha256"}
                }
                | {"file": name}
            )
    if set(expected) != expected_names:
        raise ValueError("export editing inventory contains undeclared files")
    fields = validate_fields(fields, target["store"])
    entries = [
        dict(item, locale=locale, slot=slot)
        for locale, groups in images.items()
        for slot, items in groups.items()
        for item in items
    ]
    validated = validate_images(source, entries, target["store"]) if entries else []
    for item in validated:
        if item["sha256"] != expected[item["file"]]:
            raise ValueError("metadata image changed outside the bound inventory")
        data = safe_path(source, item["file"]).read_bytes()
        if hashlib.sha256(data).hexdigest() != item["sha256"]:
            raise ValueError("import image bytes changed during validation")
        captured[item["file"]] = data
    verify_inventory(source, expected, exact=True)
    validate_public_metadata(
        {
            "schema_version": 1,
            "type": "metadata-import",
            "target": target,
            "fields": fields,
            "images": images,
            "release_notes": notes,
        },
        target,
    )
    if dry_run:
        return {"status": "dry-run", "target": target, "effects": []}
    assets_path = None
    if validated:
        assets_record = {
            "schema_version": 1,
            "type": "asset-manifest",
            "target": target,
            "assets": validated,
            "provenance": {"status": "unverified-import"},
            "inputs": expected,
            "source_export": value["source_snapshot"],
            "catalog_sha256": file_digest(CATALOG_FILE),
            "runtime": runtime_inventory(Path(__file__).resolve().parents[1]),
        }
        assets_path = publish_snapshot(state / "assets", assets_record, captured)
        prefix = assets_path.relative_to(root).as_posix()
        for groups in images.values():
            for items in groups.values():
                for item in items:
                    name = item["file"]
                    item["sha256"] = expected[name]
                    item["file"] = prefix + "/" + name
    note_files = {
        locale + "/changelogs/" + target["version"]["build"] + ".txt": text.encode(
            "utf-8"
        )
        for locale, text in notes.items()
    }
    history = publish_snapshot(
        state / "metadata",
        {
            "schema_version": 1,
            "type": "metadata-import",
            "target": target,
            "fields": fields,
            "release_notes": notes,
            "inputs": expected,
            "source_export": value["source_snapshot"],
        },
        note_files,
    )
    changelogs = {
        locale: history.relative_to(root).as_posix()
        + "/"
        + locale
        + "/changelogs/"
        + target["version"]["build"]
        + ".txt"
        for locale in notes
    }
    listing = {
        "schema_version": 1,
        "type": "metadata",
        "origin": "local",
        "target": target,
        "fields": fields,
        "images": images,
        "changelogs": changelogs,
        "release_notes": notes,
        "source_snapshot": history.relative_to(root).as_posix() + "/manifest.json",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".listing-", dir=output.parent) as tmp:
        candidate = Path(tmp) / "listing.json"
        candidate.write_bytes(canonical(listing))
        os.link(candidate, output)  # atomic, fails if another writer already created it
    return {
        "listing": output.relative_to(root).as_posix(),
        "assets": (
            assets_path.relative_to(root).as_posix() + "/manifest.json"
            if assets_path
            else None
        ),
        "snapshot": history.relative_to(root).as_posix(),
        "changelogs": changelogs,
    }
