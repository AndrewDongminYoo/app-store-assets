"""Local reviewed-file copying; independent of executors and providers."""

import shutil
from pathlib import Path

from .records import file_digest, safe_path, verify_inventory
from .snapshots import reject_snapshot_write


def stage_inventory(source, destination, expected):
    destination = Path(destination)
    if destination.resolve().is_relative_to(Path(source).resolve()):
        raise ValueError("staging destination overlaps source tree")
    if destination.is_symlink():
        raise ValueError("staging destination cannot be symlink")
    reject_snapshot_write(destination)
    destination.mkdir(parents=True)
    for name, digest in expected.items():
        original = safe_path(source, name)
        target = safe_path(destination, name)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(original, target, follow_symlinks=False)
        if file_digest(target) != digest:
            raise ValueError("input changed while staging: " + name)
        target.chmod(292)
    verify_inventory(destination, expected, exact=True)
