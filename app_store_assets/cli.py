"""Read-only offline doctor, plan and public metadata diff."""

import argparse
import json
import sys
from pathlib import Path

from .metadata import metadata_diff, resolve_changelogs
from .planning import local_context, make_plan
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
            if "version_source" in target:
                paths.append(target["version_source"]["file"])
            result = {
                "runtime": runtime,
                "target": identity,
                "inputs": inventory(root, paths),
                "effects": [],
                "remote_verified": False,
                "authenticated_account_verified": False,
                "account_id_declared": "account_id" in target,
            }
            for path, sha in captures.items():
                if result["inputs"].get(path.relative_to(root).as_posix()) != sha:
                    raise ValueError(
                        "doctor inventory differs from parsed input capture"
                    )
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
    except (ValueError, OSError, KeyError, TypeError) as error:
        print(str(error), file=sys.stderr)
        return 2
