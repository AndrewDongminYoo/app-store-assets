"""Explicit local public listing export/import with complete final validation."""

import copy
import hashlib
import re
import tempfile
from pathlib import Path

from app_store_assets.catalog import (
    CATALOG_FILE,
    encoded_format,
    validate_fields,
    validate_images,
)
from app_store_assets.contracts import (
    digest,
    exact_keys,
    image_entry,
    public_path,
    target_identity,
)
from app_store_assets.contracts import locale as validate_locale
from app_store_assets.identity import runtime_inventory
from app_store_assets.metadata import (
    IMAGE_FIELDS,
    normalize_fields,
    selected_notes,
    validate_public_metadata,
)
from app_store_assets.record_types import validate_assets
from app_store_assets.records import (
    FILE_LIMIT,
    TEXT_LIMIT,
    canonical,
    capture_bytes,
    file_digest,
    inventory,
    read_json,
    record_digest,
    safe_path,
    verify_inventory,
)
from app_store_assets.snapshots import validate_snapshot

from .budgets import CaptureBudget, bounded_json
from .outputs import preflight_output, publish_tree, write_new_file
from .publisher import publish_snapshot, snapshot_manifest

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
    root = Path(root).absolute()
    path = Path(path)
    if path.is_absolute():
        if not path.is_relative_to(root):
            raise ValueError("metadata path must stay inside the project")
        path = path.relative_to(root)
    return safe_path(root, path.as_posix())


def text_bytes(path, *, limit=TEXT_LIMIT):
    return capture_bytes(path, limit=limit)


def validate_export(value, target):
    keys = {
        "schema_version",
        "type",
        "target",
        "source_snapshot",
        "format",
        "fields",
        "images",
        "notes",
    }
    exact_keys(value, keys, keys)
    if (
        type(value["schema_version"]) is not int
        or value["schema_version"] != 1
        or value["type"] != "metadata-export"
        or value["format"] != "fastlane-repository-v1"
    ):
        raise ValueError("unsupported public metadata export format")
    identity = target_identity(value["target"])
    if identity != target_identity(target):
        raise ValueError("import target/export format differs")
    digest(value["source_snapshot"])
    names = set()
    fields = set()
    notes = set()
    for group in ("fields", "images", "notes"):
        if not isinstance(value[group], list):
            raise ValueError("invalid public export entries")
        for entry in value[group]:
            required = {"locale", "file"} | (
                {"key"}
                if group == "fields"
                else {"slot"}
                if group == "images"
                else set()
            )
            exact_keys(
                entry, required | ({"remote"} if group == "images" else set()), required
            )
            validate_locale(entry["locale"])
            try:
                public_path(entry["file"])
            except ValueError as error:
                raise ValueError("unsupported public export entry path") from error
            if entry["file"] in names:
                raise ValueError("duplicate public export path")
            names.add(entry["file"])
            if group == "fields":
                key = entry["key"]
                name = entry["locale"]
                if (
                    not isinstance(key, str)
                    or key not in FIELDS[identity["store"]]
                    or entry["file"] != name + "/" + key + ".txt"
                ):
                    raise ValueError("unsupported public metadata field/path")
                if (name, key) in fields:
                    raise ValueError("duplicate public metadata field")
                fields.add((name, key))
            elif group == "notes":
                if (
                    identity["store"] != "google"
                    or entry["file"]
                    != entry["locale"]
                    + "/changelogs/"
                    + identity["version"]["build"]
                    + ".txt"
                ):
                    raise ValueError("unsupported public changelog path")
                if entry["locale"] in notes:
                    raise ValueError("duplicate public changelog")
                notes.add(entry["locale"])
            else:
                image_entry(
                    {"locale": entry["locale"], "slot": entry["slot"]}, grouped=True
                )
                if not re.fullmatch(
                    re.escape(entry["locale"])
                    + r"/images/[A-Za-z0-9_-]+/[0-9]{2,}\.(png|jpg)",
                    entry["file"],
                ):
                    raise ValueError("unsupported public image path")
                remote = entry.get("remote", {})
                exact_keys(remote, IMAGE_FIELDS - {"file", "sha256"})
                image_entry(remote)
    return copy.deepcopy(value)


def export_metadata(
    root, snapshot, target, destination, dry_run=False, *, _context_guard=None
):
    root = Path(root).resolve()
    target = target_identity(target)
    if type(dry_run) is not bool:
        raise ValueError("invalid local export dry-run flag")
    snapshot, destination = confined(root, snapshot), confined(root, destination)
    preflight_output(destination, new=True)
    if destination.is_relative_to(snapshot):
        raise ValueError("export destination overlaps immutable source snapshot")
    captures = {}
    manifest = validate_snapshot(snapshot, captures)
    record = validate_public_metadata(manifest["record"], target)
    if record["type"] != "metadata-snapshot":
        raise ValueError("export snapshot target/type differs")
    fields = validate_fields(record.get("fields", {}), target["store"], proposed=False)
    maps = {"fields": [], "images": [], "notes": []}
    files = {}
    budget = CaptureBudget(FILE_LIMIT)
    for locale, values in fields.items():
        for key, value in values.items():
            if key not in FIELDS[target["store"]]:
                raise ValueError("unsupported repository metadata field")
            name = locale + "/" + key + ".txt"
            files[name] = budget.take(value.encode("utf-8"))
            maps["fields"].append({"locale": locale, "key": key, "file": name})
    for locale, groups in record.get("images", {}).items():
        for slot, images in groups.items():
            folder = (
                APPLE_FOLDERS.get(slot, slot) if target["store"] == "apple" else slot
            )
            for index, image in enumerate(images):
                if "file" not in image or image.get("sha256") != manifest["files"].get(
                    image["file"]
                ):
                    raise ValueError("download image annotation/hash differs")
                source = safe_path(snapshot, image["file"])
                data = budget.read(source, capture_bytes, per_file=64 * 1024 * 1024)
                if hashlib.sha256(data).hexdigest() != image["sha256"]:
                    raise ValueError("download bytes changed during export")
                with tempfile.TemporaryDirectory(prefix="public-export-image-") as home:
                    staged = Path(home).resolve() / source.name
                    staged.write_bytes(data)
                    fmt, _ = encoded_format(staged)
                name = f"{locale}/images/{folder}/{index + 1:02}." + (
                    "png" if fmt == "PNG" else "jpg"
                )
                files[name] = data
                remote = {
                    k: copy.deepcopy(v)
                    for k, v in image.items()
                    if k in IMAGE_FIELDS - {"file", "sha256"}
                }
                maps["images"].append(
                    {"locale": locale, "slot": slot, "file": name, "remote": remote}
                )
    notes = selected_notes(record) if target["store"] == "google" else {}
    for locale, text in notes.items():
        name = locale + "/changelogs/" + target["version"]["build"] + ".txt"
        files[name] = budget.take(text.encode("utf-8"))
        maps["notes"].append({"locale": locale, "file": name})
    value = validate_export(
        {
            "schema_version": 1,
            "type": "metadata-export",
            "target": target,
            "source_snapshot": record_digest(manifest),
            "format": "fastlane-repository-v1",
            **maps,
        },
        target,
    )
    export_bytes = budget.take(bounded_json(value, canonical, TEXT_LIMIT))
    # Source address, inventory and complete record must still match captured bytes.
    if validate_snapshot(snapshot) != manifest:
        raise ValueError("source snapshot changed during export")
    if _context_guard is not None:
        _context_guard()
    if dry_run:
        return {"status": "dry-run", "target": target, "effects": []}
    return publish_tree(destination, {**files, EXPORT_MANIFEST: export_bytes})


def import_metadata(
    root,
    source,
    target,
    output,
    state,
    metadata_only=False,
    dry_run=False,
    *,
    _context_guard=None,
):
    root = Path(root).resolve()
    target = target_identity(target)
    if type(metadata_only) is not bool or type(dry_run) is not bool:
        raise ValueError("invalid local import flags")
    source, output, state = (confined(root, path) for path in (source, output, state))
    preflight_output(output, new=True)
    preflight_output(state)
    if output.is_relative_to(source) or state.is_relative_to(source):
        raise ValueError("import output/history overlaps the editing tree")
    if any(
        directory.is_relative_to(output)
        for directory in (state / "metadata", state / "assets")
    ):
        raise ValueError("import output overlaps a reserved history directory")
    captures = {}
    manifest_path = safe_path(source, EXPORT_MANIFEST)
    value = validate_export(read_json(manifest_path, captures), target)
    declared = {EXPORT_MANIFEST} | {
        entry["file"]
        for group in ("fields", "images", "notes")
        for entry in value[group]
    }
    expected = inventory(source, sorted(declared))
    verify_inventory(source, expected, exact=True)
    if captures.get(manifest_path) != expected[EXPORT_MANIFEST]:
        raise ValueError("export manifest changed during import capture")

    budget = CaptureBudget(FILE_LIMIT)

    def captured_text(name):
        data = budget.read(safe_path(source, name), text_bytes, per_file=TEXT_LIMIT)
        if hashlib.sha256(data).hexdigest() != expected[name]:
            raise ValueError("metadata text changed outside bound inventory")
        return data.decode("utf-8")

    fields = {}
    images = {}
    notes = {}
    captured = {}
    for entry in value["fields"]:
        fields.setdefault(entry["locale"], {})[entry["key"]] = captured_text(
            entry["file"]
        )
    for entry in value["notes"]:
        notes[entry["locale"]] = captured_text(entry["file"])
        normalize_fields({entry["locale"]: {"release_notes": notes[entry["locale"]]}})
    for entry in value["images"]:
        if not metadata_only:
            images.setdefault(entry["locale"], {}).setdefault(entry["slot"], []).append(
                {**entry.get("remote", {}), "file": entry["file"]}
            )
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
            raise ValueError("metadata image changed outside bound inventory")
        data = budget.read(
            safe_path(source, item["file"]), capture_bytes, per_file=64 * 1024 * 1024
        )
        if hashlib.sha256(data).hexdigest() != item["sha256"]:
            raise ValueError("import image bytes changed during validation")
        captured[item["file"]] = data
    source_export = value["source_snapshot"]
    assets_record = None
    assets_path = None
    if validated:
        assets_record = validate_assets(
            {
                "schema_version": 1,
                "type": "asset-manifest",
                "target": target,
                "assets": validated,
                "provenance": {"status": "unverified-import"},
                "inputs": expected,
                "source_export": source_export,
                "catalog_sha256": file_digest(CATALOG_FILE),
                "runtime": runtime_inventory(Path(__file__).resolve().parents[1]),
            },
            target,
        )
        assets_path = (
            state / "assets" / record_digest(snapshot_manifest(assets_record, captured))
        )
        supplied = {
            item["file"]: item
            for groups in images.values()
            for items in groups.values()
            for item in items
        }
        images = {}
        for entry in validated:
            item = copy.deepcopy(supplied[entry["file"]])
            item["sha256"] = entry["sha256"]
            item["file"] = assets_path.relative_to(root).as_posix() + "/" + item["file"]
            images.setdefault(entry["locale"], {}).setdefault(entry["slot"], []).append(
                item
            )
    note_files = {
        locale + "/changelogs/" + target["version"]["build"] + ".txt": text.encode(
            "utf-8"
        )
        for locale, text in notes.items()
    }
    history_record = validate_public_metadata(
        {
            "schema_version": 1,
            "type": "metadata-import",
            "target": target,
            "fields": fields,
            "release_notes": notes,
            "inputs": expected,
            "source_export": source_export,
        },
        target,
    )
    history = (
        state
        / "metadata"
        / record_digest(snapshot_manifest(history_record, note_files))
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
    listing = validate_public_metadata(
        {
            "schema_version": 1,
            "type": "metadata",
            "origin": "local",
            "target": target,
            "fields": fields,
            "images": images,
            "changelogs": changelogs,
            "release_notes": notes,
            "source_snapshot": history.relative_to(root).as_posix() + "/manifest.json",
        },
        target,
    )
    verify_inventory(source, expected, exact=True)
    if (
        state.is_relative_to(output)
        or output.is_relative_to(history)
        or history.is_relative_to(output)
        or (
            assets_path is not None
            and (
                output.is_relative_to(assets_path) or assets_path.is_relative_to(output)
            )
        )
    ):
        raise ValueError("import output/history overlaps immutable publication")
    preflight_output(state)
    preflight_output(output, new=True)
    listing_bytes = bounded_json(listing, canonical, TEXT_LIMIT)
    if _context_guard is not None:
        _context_guard()
    if dry_run:
        return {"status": "dry-run", "target": target, "effects": []}
    if assets_record is not None:
        if (
            publish_snapshot(
                state / "assets", assets_record, captured, _context_guard=_context_guard
            )
            != assets_path
        ):
            raise ValueError("asset publication address changed")
    if (
        publish_snapshot(
            state / "metadata",
            history_record,
            note_files,
            _context_guard=_context_guard,
        )
        != history
    ):
        raise ValueError("metadata publication address changed")
    if _context_guard is not None:
        _context_guard()
    write_new_file(output, listing_bytes)
    return {
        "listing": output.relative_to(root).as_posix(),
        "assets": assets_path.relative_to(root).as_posix() + "/manifest.json"
        if assets_path
        else None,
        "snapshot": history.relative_to(root).as_posix(),
        "changelogs": changelogs,
    }
