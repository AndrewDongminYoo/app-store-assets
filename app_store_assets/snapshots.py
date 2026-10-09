"""Read-only content-addressed public history validation."""

from pathlib import Path

from .contracts import digest, exact_keys, hash_inventory
from .record_types import validate_record
from .records import file_digest, read_json, record_digest, tree_inventory


def validate_snapshot(folder, captures=None):
    folder = Path(folder).absolute()
    observed = {} if captures is None else captures
    manifest_path = folder / "manifest.json"
    manifest = read_json(manifest_path, observed)
    keys = {"schema_version", "type", "record", "files"}
    exact_keys(manifest, keys, keys)
    if (
        type(manifest["schema_version"]) is not int
        or manifest["schema_version"] != 1
        or manifest["type"] != "snapshot"
    ):
        raise ValueError("unsupported snapshot manifest")
    hash_inventory(manifest["files"])
    if "manifest.json" in manifest["files"]:
        raise ValueError("snapshot content may not replace its manifest")
    digest(folder.name)
    if folder.name != record_digest(manifest):
        raise ValueError("snapshot content address differs from manifest")
    # Validation must not rewrite the bytes used for the content address.
    record = validate_record(manifest["record"])
    actual = tree_inventory(folder, exclude_root=("manifest.json",))
    if actual != manifest["files"]:
        raise ValueError("snapshot inventory/hash differs from manifest")
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
            item["file"] not in actual or item.get("sha256") != actual[item["file"]]
        ):
            raise ValueError(
                "snapshot image annotation differs from captured inventory"
            )
    if record["type"] == "asset-manifest":
        from .catalog import validate_images

        validate_images(folder, record["assets"], record["target"]["store"])
    else:
        from .decoding import image_info

        for item in entries:
            if "file" in item and any(
                key in item for key in ("width", "height", "size")
            ):
                width, height, _ = image_info(folder / item["file"])
                for key, value in (
                    ("width", width),
                    ("height", height),
                    ("size", [width, height]),
                ):
                    if key in item and item[key] != value:
                        raise ValueError(
                            "snapshot image dimensions differ from captured bytes"
                        )
                if file_digest(folder / item["file"]) != actual[item["file"]]:
                    raise ValueError(
                        "snapshot image changed during dimension validation"
                    )
    if file_digest(manifest_path) != observed[manifest_path]:
        raise ValueError("snapshot manifest changed after capture")
    if captures is not None:
        from .records import bind_capture

        for name, sha in actual.items():
            bind_capture(captures, folder / name, sha)
    return manifest
