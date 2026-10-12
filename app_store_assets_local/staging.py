"""Copy only captured reviewed public bytes to a new local directory."""

import hashlib
from pathlib import Path

from app_store_assets.contracts import hash_inventory
from app_store_assets.records import (
    FILE_LIMIT,
    capture_bytes,
    open_directory,
    safe_path,
    verify_inventory,
)

from .budgets import CaptureBudget
from .outputs import preflight_output, publish_tree


def stage_inventory(source, destination, expected):
    source = Path(source).absolute()
    destination = Path(destination).absolute()
    hash_inventory(expected)
    # Even an empty inventory must validate the source root without symlinks.
    try:
        with open_directory(source):
            pass
    except OSError as error:
        raise ValueError("unsafe staging source root") from error
    if destination.is_relative_to(source) or destination.resolve().is_relative_to(
        source.resolve()
    ):
        raise ValueError("staging destination overlaps source tree")
    preflight_output(destination, new=True)
    budget = CaptureBudget(FILE_LIMIT)
    captured = {
        name: budget.read(safe_path(source, name), capture_bytes) for name in expected
    }
    if sum(map(len, captured.values())) > FILE_LIMIT:
        raise ValueError("staging exceeds total byte bound")
    if {
        name: hashlib.sha256(data).hexdigest() for name, data in captured.items()
    } != expected:
        raise ValueError("input changed while staging")
    publish_tree(destination, captured, mode=0o444)
    verify_inventory(destination, expected, exact=True)
