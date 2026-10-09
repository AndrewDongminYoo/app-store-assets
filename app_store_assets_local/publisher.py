"""Immutable local snapshots of complete public records and captured bytes."""

import copy
import hashlib
import tempfile
from pathlib import Path

from app_store_assets.contracts import hash_inventory, public_path
from app_store_assets.record_types import validate_record
from app_store_assets.records import FILE_LIMIT, canonical, capture_bytes, record_digest
from app_store_assets.snapshots import validate_snapshot

from .outputs import preflight_output, publish_tree


def snapshot_manifest(record, files):
    validate_record(record)
    if not isinstance(files, dict):
        raise ValueError("invalid snapshot files mapping")
    hashes = {}
    total = 0
    for name, data in files.items():
        public_path(name)
        if name == "manifest.json":
            raise ValueError("snapshot content may not replace manifest")
        if not isinstance(data, bytes):
            raise ValueError("snapshot requires captured bytes")
        total += len(data)
        if total > FILE_LIMIT:
            raise ValueError("snapshot exceeds total captured byte bound")
        hashes[name] = hashlib.sha256(data).hexdigest()
    entries = (
        record.get("assets", [])
        if record["type"] == "asset-manifest"
        else [
            item
            for groups in record.get("images", {}).values()
            for images in groups.values()
            for item in images
        ]
    )
    for item in entries:
        if "file" in item and (
            item["file"] not in hashes or item.get("sha256") != hashes[item["file"]]
        ):
            raise ValueError(
                "snapshot image annotation differs from captured inventory"
            )
    # Decode only owned ephemeral captures before creating durable history.
    if entries:
        with tempfile.TemporaryDirectory(prefix="public-snapshot-images-") as home:
            folder = Path(home).resolve()
            for item in entries:
                if "file" not in item:
                    continue
                path = folder / item["file"]
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(files[item["file"]])
            if record["type"] == "asset-manifest":
                from app_store_assets.catalog import validate_images

                validate_images(folder, record["assets"], record["target"]["store"])
            else:
                from app_store_assets.decoding import image_info

                for item in entries:
                    if "file" not in item:
                        continue
                    width, height, _ = image_info(folder / item["file"])
                    for key, value in (
                        ("width", width),
                        ("height", height),
                        ("size", [width, height]),
                    ):
                        if key in item and item[key] != value:
                            raise ValueError(
                                "snapshot dimensions differ from captured bytes"
                            )
    return {
        "schema_version": 1,
        "type": "snapshot",
        "record": copy.deepcopy(record),
        "files": hashes,
    }


def publish_snapshot(root, record, files, expected_hashes=None, *, _context_guard=None):
    if not isinstance(files, dict):
        raise ValueError("invalid snapshot files mapping")
    for name, source in files.items():
        public_path(name)
        if not isinstance(source, (bytes, str, Path)):
            raise ValueError("unsupported snapshot source")
    validate_record(record)
    if expected_hashes is not None:
        hash_inventory(expected_hashes)
        if set(expected_hashes) != set(files):
            raise ValueError("snapshot inspected inventory differs")
    captured = {
        name: data if isinstance(data, bytes) else capture_bytes(data, limit=FILE_LIMIT)
        for name, data in files.items()
    }
    manifest = snapshot_manifest(record, captured)
    if expected_hashes is not None and manifest["files"] != expected_hashes:
        raise ValueError("published artifact hash differs from inspected digest")
    if _context_guard is not None:
        _context_guard()
    root = preflight_output(root)
    destination = root / record_digest(manifest)

    def winner(path):
        if validate_snapshot(path) != manifest:
            raise ValueError("existing snapshot cache differs from expected manifest")

    publish_tree(
        destination,
        {**captured, "manifest.json": canonical(manifest)},
        reuse=winner,
        mode=0o444,
    )
    winner(destination)
    return destination
