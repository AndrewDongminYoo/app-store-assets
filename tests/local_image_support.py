"""Synthetic metadata snapshots with images for local export/import tests."""

import hashlib

from test_offline_boundaries import snapshot_fixture


def image_snapshot(root, target, images, slot="APP_IPHONE_67"):
    files = {}
    items = []
    for index, data in enumerate(images):
        name = f"images/public-{index}.png"
        files[name] = data
        items.append({"file": name, "sha256": hashlib.sha256(data).hexdigest()})
    record = {
        "schema_version": 1,
        "type": "metadata-snapshot",
        "target": target,
        "fields": {},
        "images": {"en-US": {slot: items}},
    }
    return snapshot_fixture(root / "downloads", record, files)
