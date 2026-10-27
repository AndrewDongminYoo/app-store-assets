"""Verify a transfer approval and stage checked bytes without store access."""

import argparse
import hashlib
import os
import subprocess
import sys
from pathlib import Path

from app_store_assets.cli import check_captures
from app_store_assets.contracts import digest, exact_keys, target_identity
from app_store_assets.decoding import IMAGE_LIMIT
from app_store_assets.planning import verify_plan
from app_store_assets.records import (
    FILE_LIMIT,
    TEXT_LIMIT,
    canonical,
    capture_bytes,
    digest_stream,
    open_directory,
    read_json,
    safe_path,
)

from .budgets import CaptureBudget, bounded_json


def validate_approval(plan, approval):
    keys = {"schema_version", "type", "plan_digest", "target", "operation"}
    try:
        exact_keys(approval, keys, keys)
    except ValueError:
        raise ValueError("approval has unknown or missing keys") from None
    if (
        type(approval["schema_version"]) is not int
        or approval["schema_version"] != 1
        or approval["type"] != "transfer-approval"
    ):
        raise ValueError("unsupported approval schema/type")
    digest(approval["plan_digest"])
    if approval["plan_digest"] != plan["digest"]:
        raise ValueError("approval plan digest differs")
    if approval["operation"] != "images":
        raise ValueError("approval operation must be images")
    identity = target_identity(approval["target"])
    payload = plan["payload"]
    if identity != payload["target"]:
        raise ValueError("approval target differs from the whole plan target")
    if (
        payload["operation"] != "images"
        or identity["store"] != "apple"
        or identity["platform"] != "ios"
    ):
        raise ValueError("transfer requires an Apple iOS images plan")
    if (payload.get("assets") or {}).get("provenance") != {
        "status": "unverified-import"
    }:
        raise ValueError(
            "transfer requires an immutable unverified-import asset snapshot"
        )


def stage_transfer(root, plan_path, approval_path, staging_dir):
    """The caller owns the empty private directory and removes it after use."""
    root = Path(root).resolve()
    captures = {}
    plan = read_json(safe_path(root, plan_path), captures)
    approval = read_json(safe_path(root, approval_path), captures)
    verify_plan(root, plan)
    validate_approval(plan, approval)
    check_captures(captures)
    stage = Path(staging_dir)
    if not stage.is_absolute():
        raise ValueError("staging directory must be an absolute path")
    if ".." in stage.parts:
        raise ValueError(
            "staging directory must use a canonical path without parent traversal"
        )
    runtime = Path(__file__).resolve().parents[1]
    if any(stage.is_relative_to(boundary) for boundary in (root, runtime)):
        raise ValueError("staging directory must be outside the project and runtime")
    payload = plan["payload"]
    result = {
        "schema_version": 1,
        "type": "verified-transfer-intent",
        "plan_digest": plan["digest"],
        "target": payload["target"],
        "operation": "images",
        "mode": payload["mode"],
        "remote_verified": False,
        "remote": payload["remote"],
        "replacement": payload["replacement"],
        "provenance": payload["assets"]["provenance"],
        "groups": [],
    }
    budget = CaptureBudget(FILE_LIMIT)
    with open_directory(stage) as directory:
        before = os.fstat(directory)
        if before.st_uid != os.getuid() or before.st_mode & 0o077:
            raise ValueError("staging directory must be private and owned by this user")
        if os.listdir(directory):
            raise ValueError("staging directory must be empty")
        created = []
        try:
            for locale, groups in payload["listing"]["images"].items():
                for slot, images in groups.items():
                    group = {"locale": locale, "slot": slot, "images": []}
                    for image in images:
                        source = safe_path(root, image["file"])
                        data = budget.read(source, capture_bytes, per_file=IMAGE_LIMIT)
                        sha = hashlib.sha256(data).hexdigest()
                        if sha != image["sha256"]:
                            raise ValueError(f"image SHA-256 differs: {locale}/{slot}")
                        name = f"{len(created):06d}{source.suffix}"
                        fd = os.open(
                            name,
                            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                            0o600,
                            dir_fd=directory,
                        )
                        observed = os.fstat(fd)
                        created.append((name, (observed.st_dev, observed.st_ino), sha))
                        with os.fdopen(fd, "wb") as output:
                            output.write(data)
                        group["images"].append(
                            {
                                "staged_path": str(stage / name),
                                "sha256": sha,
                                "md5": hashlib.md5(data).hexdigest(),
                            }
                        )
                    result["groups"].append(group)
            check_captures(captures)
            for name, expected_inode, expected_sha in created:
                fd = os.open(
                    name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory
                )
                with os.fdopen(fd, "rb") as staged:
                    observed = os.fstat(staged.fileno())
                    if (
                        observed.st_dev,
                        observed.st_ino,
                    ) != expected_inode or digest_stream(
                        staged, IMAGE_LIMIT
                    ) != expected_sha:
                        raise ValueError("staged file changed during verification")
            with open_directory(stage) as current:
                now = os.fstat(current)
                if (now.st_dev, now.st_ino) != (before.st_dev, before.st_ino):
                    raise ValueError("staging directory changed during verification")
            bounded_json(result, lambda value: canonical(value) + b"\n", TEXT_LIMIT)
            return result
        except BaseException:
            for name, expected_inode, _ in created:
                try:
                    observed = os.stat(name, dir_fd=directory, follow_symlinks=False)
                except FileNotFoundError:
                    continue
                if (observed.st_dev, observed.st_ino) == expected_inode:
                    os.unlink(name, dir_fd=directory)
            raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True)
    parser.add_argument("--plan", required=True)
    parser.add_argument("--approval", required=True)
    parser.add_argument("--staging-dir", required=True)
    args = parser.parse_args(argv)
    try:
        result = stage_transfer(args.root, args.plan, args.approval, args.staging_dir)
        print(canonical(result).decode("utf-8"))
        return 0
    except (
        ValueError,
        OSError,
        KeyError,
        TypeError,
        RecursionError,
        subprocess.SubprocessError,
    ) as error:
        print(str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
