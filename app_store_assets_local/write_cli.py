"""Explicit local import/export; no store/provider/native execution."""

import argparse
import json
import sys
from pathlib import Path

from app_store_assets.cli import check_captures
from app_store_assets.planning import local_context
from app_store_assets.profiles import target_identity

from .metadata_io import confined, export_metadata, import_metadata


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("import", "export"))
    parser.add_argument("--root", default=".")
    parser.add_argument("--profile", default="store-upload.json")
    parser.add_argument("--target", required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--state", default="build/store-assets")
    parser.add_argument("--metadata-only", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    try:
        root = Path(args.root).resolve()
        captures = {}
        _, target, _ = local_context(root, args.profile, args.target, captures)
        identity = target_identity(target)
        check_captures(captures)

        def guard():
            check_captures(captures)
            local_context(root, args.profile, args.target, captures)

        source = confined(root, args.source)
        if args.command == "export":
            if source.name == "manifest.json":
                source = source.parent
            result = export_metadata(
                root,
                source,
                identity,
                args.output,
                dry_run=args.dry_run,
                _context_guard=guard,
            )
            if not args.dry_run:
                result = {"directory": result.relative_to(root).as_posix()}
        else:
            result = import_metadata(
                root,
                source,
                identity,
                args.output,
                args.state,
                args.metadata_only,
                dry_run=args.dry_run,
                _context_guard=guard,
            )
        print(json.dumps(result, sort_keys=True, ensure_ascii=False))
        return 0
    except (ValueError, OSError, KeyError, TypeError) as error:
        print(str(error), file=sys.stderr)
        return 2
