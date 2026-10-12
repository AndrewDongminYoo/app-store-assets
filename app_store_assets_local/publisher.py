"""Immutable local snapshots of complete public records and captured bytes."""

import copy
import hashlib
import tempfile
from pathlib import Path

from app_store_assets.contracts import hash_inventory, public_path
from app_store_assets.decoding import IMAGE_LIMIT
from app_store_assets.record_types import validate_record
from app_store_assets.records import (
    FILE_LIMIT,
    TEXT_LIMIT,
    canonical,
    capture_bytes,
    check_walk_bounds,
    record_digest,
    safe_path,
)
from app_store_assets.snapshots import validate_snapshot

from .budgets import CaptureBudget, bounded_json
from .outputs import preflight_output, publish_tree


def local_record(record):
    validate_record(record)
    if record["type"] not in {
        "metadata",
        "metadata-snapshot",
        "metadata-import",
        "asset-manifest",
    }:
        raise ValueError("local publication supports only metadata and asset records")
    if record.get("changelogs"):
        raise ValueError("local publication keeps release notes inline")


def image_entries(record):
    return (
        record.get("assets", [])
        if record["type"] == "asset-manifest"
        else [
            item
            for groups in record.get("images", {}).values()
            for images in groups.values()
            for item in images
        ]
    )


def snapshot_manifest(record, files):
    local_record(record)
    if not isinstance(files, dict):
        raise ValueError("invalid snapshot files mapping")
    entries = image_entries(record)
    image_names = {item["file"] for item in entries if "file" in item}
    hashes = {}
    total = 0
    for name, data in files.items():
        public_path(name)
        if name == "manifest.json":
            raise ValueError("snapshot content may not replace manifest")
        if not isinstance(data, bytes):
            raise ValueError("snapshot requires captured bytes")
        if name in image_names and len(data) > IMAGE_LIMIT:
            raise ValueError("snapshot image exceeds individual byte bound")
        if name not in image_names and len(data) > TEXT_LIMIT:
            raise ValueError("snapshot text exceeds individual byte bound")
        total += len(data)
        if total > FILE_LIMIT:
            raise ValueError("snapshot exceeds total captured byte bound")
        hashes[name] = hashlib.sha256(data).hexdigest()
    for item in entries:
        if "file" in item and (
            item["file"] not in hashes or item.get("sha256") != hashes[item["file"]]
        ):
            raise ValueError(
                "snapshot image annotation differs from captured inventory"
            )
    manifest = {
        "schema_version": 1,
        "type": "snapshot",
        "record": copy.deepcopy(record),
        "files": hashes,
    }
    bounded_json(manifest, canonical, TEXT_LIMIT)
    # Decode only owned ephemeral captures before creating durable history.
    if entries:
        with tempfile.TemporaryDirectory(prefix="public-snapshot-images-") as home:
            folder = Path(home).resolve()
            staged = set()
            for item in entries:
                if "file" not in item:
                    continue
                if item["file"] in staged:
                    continue
                path = folder / item["file"]
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(files[item["file"]])
                staged.add(item["file"])
            if record["type"] == "asset-manifest":
                from app_store_assets.catalog import validate_images

                validate_images(
                    folder,
                    record["assets"],
                    record["target"]["store"],
                    record["target"]["platform"],
                )
            else:
                from app_store_assets.decoding import image_bytes, image_info

                decoded = {}
                checked = set()
                for item in entries:
                    if "file" not in item:
                        continue
                    name = item["file"]
                    staged_path = safe_path(folder, name)
                    if name not in checked:
                        # Every file keeps its own signature/name/extension check.
                        image_bytes(staged_path, expected_sha256=hashes[name])
                        checked.add(name)
                    # Decoding depends only on bytes, so one content hash decodes once.
                    if hashes[name] not in decoded:
                        decoded[hashes[name]] = image_info(
                            staged_path, expected_sha256=hashes[name]
                        )
                    width, height, _ = decoded[hashes[name]]
                    for key, value in (
                        ("width", width),
                        ("height", height),
                        ("size", [width, height]),
                    ):
                        if key in item and item[key] != value:
                            raise ValueError(
                                "snapshot dimensions differ from captured bytes"
                            )
    return manifest


def publish_snapshot(root, record, files, expected_hashes=None, *, _context_guard=None):
    if not isinstance(files, dict):
        raise ValueError("invalid snapshot files mapping")
    for name, source in files.items():
        public_path(name)
        if not isinstance(source, (bytes, str, Path)):
            raise ValueError("unsupported snapshot source")
    # The snapshot tree holds the files plus its manifest; reject before writing.
    check_walk_bounds({*files, "manifest.json"})
    local_record(record)
    image_names = {item["file"] for item in image_entries(record) if "file" in item}
    if expected_hashes is not None:
        hash_inventory(expected_hashes)
        if set(expected_hashes) != set(files):
            raise ValueError("snapshot inspected inventory differs")
    root = preflight_output(root, directory_root=True)
    budget = CaptureBudget(FILE_LIMIT)
    captured = {}
    for name, source in files.items():
        if isinstance(source, bytes):
            if name in image_names and len(source) > IMAGE_LIMIT:
                raise ValueError("snapshot image exceeds individual byte bound")
            if name not in image_names and len(source) > TEXT_LIMIT:
                raise ValueError("snapshot text exceeds individual byte bound")
            captured[name] = budget.take(source)
    for name, source in files.items():
        if not isinstance(source, bytes):
            captured[name] = budget.read(
                source,
                capture_bytes,
                per_file=IMAGE_LIMIT if name in image_names else TEXT_LIMIT,
            )
    manifest = snapshot_manifest(record, captured)
    manifest_bytes = bounded_json(manifest, canonical, TEXT_LIMIT)
    if expected_hashes is not None and manifest["files"] != expected_hashes:
        raise ValueError("published artifact hash differs from inspected digest")
    if _context_guard is not None:
        _context_guard()
    root = preflight_output(root, directory_root=True)
    destination = root / record_digest(manifest)

    def winner(path):
        if validate_snapshot(path, total_limit=FILE_LIMIT) != manifest:
            raise ValueError("existing snapshot cache differs from expected manifest")

    publish_tree(
        destination,
        {**captured, "manifest.json": manifest_bytes},
        reuse=winner,
        mode=0o444,
    )
    winner(destination)
    return destination
