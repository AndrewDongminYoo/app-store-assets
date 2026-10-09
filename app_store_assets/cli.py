"""Offline doctor/plan and explicit local metadata import/export/diff."""

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

from .metadata import metadata_diff, validate_public_metadata
from .metadata_io import export_metadata, import_metadata
from .planning import local_context, make_plan
from .profiles import target_identity
from .records import file_digest, inventory, read_json, safe_path
from .snapshots import validate_snapshot


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("command", choices=("doctor", "plan", "diff", "import", "export"))
    p.add_argument("--root", default=".")
    p.add_argument("--profile", default="store-upload.json")
    p.add_argument("--target", required=True)
    p.add_argument(
        "--operation", choices=("binary", "metadata", "images"), default="binary"
    )
    for name in ("source", "output", "before", "after"):
        p.add_argument("--" + name)
    p.add_argument("--state", default="build/store-assets")
    p.add_argument("--metadata-only", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    return p


def metadata_input(root, name, target):
    path = safe_path(root, name)
    record = read_json(path)
    if record.get("type") == "snapshot":
        if path.name != "manifest.json":
            raise ValueError("snapshot input must name manifest.json")
        record = validate_snapshot(path.parent)["record"]
    record = validate_public_metadata(record, target)
    if record.get("changelogs"):
        notes = {}
        for locale, name in record["changelogs"].items():
            note_path = safe_path(root, name)
            # A referenced immutable note must not bypass its own snapshot guard.
            for parent in note_path.parents:
                if parent == Path(root).resolve():
                    break
                if len(parent.name) == 64 and (parent / "manifest.json").exists():
                    validate_snapshot(parent)
            expected = file_digest(note_path)
            with os.fdopen(
                os.open(note_path, os.O_RDONLY | os.O_NOFOLLOW), "rb"
            ) as stream:
                data = stream.read(8 * 1024 * 1024 + 1)
            if (
                len(data) > 8 * 1024 * 1024
                or hashlib.sha256(data).hexdigest() != expected
            ):
                raise ValueError("local changelog changed during capture")
            notes[locale] = data.decode("utf-8")
        record["release_notes"] = notes
        record = validate_public_metadata(record, target)
    return record


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        root = Path(args.root).resolve()
        profile, target, runtime = local_context(root, args.profile, args.target)
        identity = target_identity(target)
        if args.command == "doctor":
            result = {
                "runtime": runtime,
                "target": identity,
                "inputs": inventory(root, [args.profile, *target["inputs"]]),
                "effects": [],
                "remote_verified": False,
                "authenticated_account_verified": False,
                "account_id_declared": "account_id" in target,
            }
        elif args.command == "plan":
            result = make_plan(root, args.profile, args.target, args.operation)
        elif args.command == "diff":
            if not args.before or not args.after:
                raise ValueError("diff requires --before and --after")
            a, b = (
                metadata_input(root, p, identity) for p in (args.before, args.after)
            )
            if a.get("target") != identity or b.get("target") != identity:
                raise ValueError("diff target differs from selected target")
            result = metadata_diff(a, b)
        else:
            if not args.source or not args.output:
                raise ValueError(args.command + " requires --source and new --output")
            source = safe_path(root, args.source)
            if args.command == "export":
                if source.is_file():
                    if source.name != "manifest.json":
                        raise ValueError("source must be snapshot/manifest.json")
                    source = source.parent
                path = export_metadata(
                    root, source, identity, args.output, dry_run=args.dry_run
                )
                result = (
                    path
                    if args.dry_run
                    else {"directory": path.relative_to(root).as_posix()}
                )
            else:
                result = import_metadata(
                    root,
                    source,
                    identity,
                    args.output,
                    safe_path(root, args.state),
                    args.metadata_only,
                    dry_run=args.dry_run,
                )
        print(json.dumps(result, sort_keys=True, ensure_ascii=False))
        return 0
    except (ValueError, OSError, KeyError, TypeError) as error:
        print(str(error), file=sys.stderr)
        return 2
