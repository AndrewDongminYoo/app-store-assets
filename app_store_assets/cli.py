"""Read-only offline doctor, plan and public metadata diff."""

import argparse
import json
import subprocess
import sys
from pathlib import Path

from .metadata import metadata_diff, resolve_changelogs
from .planning import check_asset_inventory, doctor_assets, local_context, make_plan
from .profiles import target_identity
from .records import inventory, read_json, safe_path
from .snapshots import validate_snapshot


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("command", choices=("doctor", "plan", "diff"))
    p.add_argument("--root", default=".")
    p.add_argument("--profile", default="store-upload.json")
    p.add_argument("--target", required=True)
    p.add_argument(
        "--operation", choices=("binary", "metadata", "images"), default="binary"
    )
    for name in ("before", "after"):
        p.add_argument("--" + name)
    p.add_argument("--dry-run", action="store_true")
    return p


def check_captures(captures):
    from .records import file_digest

    for path, sha in captures.items():
        if file_digest(path) != sha:
            raise ValueError("parsed public input changed before result")


def metadata_input(root, name, target, captures=None):
    captures = {} if captures is None else captures
    path = safe_path(root, name)
    content_root = root
    record = read_json(path, captures)
    if isinstance(record, dict) and record.get("type") == "snapshot":
        if path.name != "manifest.json":
            raise ValueError("snapshot input must name manifest.json")
        record = validate_snapshot(path.parent, captures)["record"]
        content_root = path.parent
    record = resolve_changelogs(
        root, record, target, captures, content_root=content_root
    )
    check_captures(captures)
    return record


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        root = Path(args.root).resolve()
        captures = {}
        profile, target, runtime = local_context(
            root, args.profile, args.target, captures
        )
        identity = target_identity(target)
        if args.command == "doctor":
            paths = [args.profile, *target["inputs"]]
            asset_directories = []
            requested_files = set()
            requested_directories = set()
            if "version_source" in target:
                paths.append(target["version_source"]["file"])
            if target.get("assets"):
                asset_directories = doctor_assets(root, target, captures)
                paths.extend(asset_directories)
                paths.extend(path.relative_to(root).as_posix() for path in captures)
                requested = set(paths)
                for name in requested:
                    path = safe_path(root, name)
                    if path.is_file():
                        requested_files.add(name)
                    elif path.is_dir():
                        requested_directories.add(name)
                    else:
                        raise ValueError("missing bound input or unsupported input type")
                paths = [
                    name for name in sorted(requested)
                    if not any(parent.as_posix() in requested for parent in Path(name).parents)
                ]
            result = {
                "runtime": runtime,
                "target": identity,
                "inputs": inventory(root, paths),
                "effects": [],
                "remote_verified": False,
                "authenticated_account_verified": False,
                "account_id_declared": "account_id" in target,
            }
            if not requested_files.issubset(result["inputs"]):
                raise ValueError("missing bound input after inventory")
            if any(not safe_path(root, name).is_dir() for name in requested_directories):
                raise ValueError("missing bound input directory after inventory")
            for path, sha in captures.items():
                if result["inputs"].get(path.relative_to(root).as_posix()) != sha:
                    raise ValueError(
                        "doctor inventory differs from parsed input capture"
                    )
            for directory in asset_directories:
                check_asset_inventory(root, directory, result["inputs"], captures)
        elif args.command == "plan":
            result = make_plan(root, args.profile, args.target, args.operation)
        else:
            if not args.before or not args.after:
                raise ValueError("diff requires --before and --after")
            before = metadata_input(root, args.before, identity, captures)
            after = metadata_input(root, args.after, identity, captures)
            result = metadata_diff(before, after)
        check_captures(captures)
        print(json.dumps(result, sort_keys=True, ensure_ascii=False))
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
