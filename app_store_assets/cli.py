"""Effect-separated CLI for pinned consumer profiles."""
import argparse
import json
import sys
import tempfile
from pathlib import Path

from .builds import build
from .execution import execute, readback_matches, seal_stage, stage_inventory, write_record
from .identity import runtime_identity, runtime_inventory
from .metadata import download_snapshot, metadata_diff
from .planning import make_plan
from .profiles import load_profile, provider_input_paths, target_identity
from .providers import CAPABILITIES, CommandProvider
from .records import read_json, record_digest, safe_path, verify_inventory
from .snapshots import validate_snapshot
from .generation import generate, regenerate
from .metadata_io import export_metadata, import_metadata


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument('command', choices=('doctor', 'plan', 'diff', 'generate', 'regenerate', 'build', 'download', 'export', 'import', 'execute', 'verify'))
    result.add_argument('--root', default='.')
    result.add_argument('--profile', default='store-upload.json')
    result.add_argument('--target', required=True)
    result.add_argument('--operation', choices=('binary', 'metadata', 'images'), default='binary')
    result.add_argument('--plan')
    result.add_argument('--expected-digest')
    result.add_argument('--receipt')
    result.add_argument('--before')
    result.add_argument('--after')
    result.add_argument('--recipe')
    result.add_argument('--source')
    result.add_argument('--output')
    result.add_argument('--metadata-only', action='store_true')
    result.add_argument('--state', default='build/store-assets')
    result.add_argument('--auth-file')
    result.add_argument('--allow-build', action='store_true')
    result.add_argument('--signing-file')
    result.add_argument('--allow-effects', action='store_true')
    result.add_argument('--dry-run', action='store_true')
    return result


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        root = Path(args.root).resolve()
        profile, target = load_profile(root, args.profile, args.target)
        runtime = runtime_identity(safe_path(root, profile['runtime']['path']), profile['runtime'])
        if runtime_inventory(Path(__file__).resolve().parents[1]) != runtime['files']:
            raise ValueError('executing runtime differs from the consumer pin')
        state = safe_path(root, args.state)
        identity = target_identity(target)
        if args.command == 'doctor':
            result = {'runtime': runtime, 'target': identity, 'effects': [],
                      'capabilities': CAPABILITIES[target['store']], 'remote_verified': False,
                      'account_bound': bool(target.get('account_id'))}
        elif args.command == 'plan':
            result = make_plan(root, args.profile, args.target, args.operation)
        elif args.command == 'diff':
            if not args.before or not args.after:
                raise ValueError('diff requires --before and --after records')
            a, b = read_json(safe_path(root, args.before)), read_json(safe_path(root, args.after))
            result = metadata_diff(a.get('record', a), b.get('record', b))
        elif args.command in ('export', 'import', 'regenerate'):
            if args.dry_run:
                result = {'status': 'dry-run', 'target': identity, 'effects': ['local-' + args.command]}
            else:
                if not args.source:
                    raise ValueError(args.command + ' requires --source')
                source = safe_path(root, args.source)
                if args.command == 'import':
                    if not args.output:
                        raise ValueError('import requires a new --output listing file')
                    result = import_metadata(root, source, identity, args.output, state, args.metadata_only)
                else:
                    if source.is_file():
                        if source.name != 'manifest.json':
                            raise ValueError('source must be a snapshot directory or its manifest.json')
                        source = source.parent
                    if args.command == 'export':
                        if not args.output:
                            raise ValueError('export requires a new --output directory')
                        path = export_metadata(root, source, identity, args.output)
                        result = {'directory': path.relative_to(root).as_posix()}
                    else:
                        if args.recipe:
                            if args.recipe not in profile.get('recipes', {}):
                                raise ValueError('select a declared generation recipe')
                            recipe = read_json(safe_path(root, profile['recipes'][args.recipe]))
                            recipe['target'] = target
                        else:
                            recipe = validate_snapshot(source)['record'].get('recipe')
                        if not recipe or target_identity(recipe['target']) != identity:
                            raise ValueError('regeneration requires the original recipe and exact selected target')
                        result = regenerate(root, recipe, source, state / 'assets')
                        result['snapshot'] = result['snapshot'].relative_to(root).as_posix()
        elif args.command in ('generate', 'build'):
            if args.dry_run:
                result = {'status': 'dry-run', 'target': identity, 'effects': ['local-' + args.command]}
                if args.command == 'build':
                    adapter = profile.get('builds', {}).get(target.get('build'))
                    if not adapter:
                        raise ValueError('select a declared build-only adapter')
                    result.update(adapter_argv=adapter['argv'], inspection_argv=adapter.get('inspect_argv'),
                                  declared_inputs=adapter['inputs'], native_authority_required=profile['mode'] != 'fixture')
            elif args.command == 'generate':
                name = args.recipe or target.get('recipe')
                if name not in profile.get('recipes', {}):
                    raise ValueError('select a declared generation recipe')
                recipe = read_json(safe_path(root, profile['recipes'][name]))
                if recipe.get('target') and target_identity(recipe['target']) != identity:
                    raise ValueError('generation recipe target differs')
                recipe['target'] = target
                path = generate(root, recipe, state / 'assets')
                result = {'snapshot': path.relative_to(root).as_posix(), 'manifest': validate_snapshot(path)}
            else:
                name = target.get('build')
                if name not in profile.get('builds', {}):
                    raise ValueError('select a declared build-only adapter')
                path = build(root, target, profile['builds'][name], state / 'builds', profile['mode'],
                             args.allow_build, args.signing_file)
                result = {'snapshot': path.relative_to(root).as_posix(), 'manifest': validate_snapshot(path)}
        elif args.command == 'execute':
            if not args.plan or not args.expected_digest:
                raise ValueError('execute requires a reviewed plan and expected digest')
            plan = read_json(safe_path(root, args.plan))
            if runtime != plan['payload']['runtime']:
                raise ValueError('executing runtime differs from reviewed plan')
            if plan['payload']['target_name'] != args.target or plan['payload']['profile'] != args.profile:
                raise ValueError('execution target/profile differs from plan')
            receipt_path = safe_path(root, args.receipt) if args.receipt else None
            if receipt_path and receipt_path.exists():
                raise ValueError('receipt output already exists; preserve previous evidence')
            provider = None if args.dry_run else CommandProvider.from_plan(plan, args.allow_effects, args.auth_file)
            result = execute(root, plan, args.expected_digest, provider, state, args.dry_run)
            if args.receipt and not args.dry_run:
                receipt_path.parent.mkdir(parents=True, exist_ok=True)
                write_record(receipt_path, result)
        elif args.command == 'download':
            if args.dry_run:
                result = {'status': 'dry-run', 'effects': [], 'target': identity}
            else:
                provider = CommandProvider(target, profile['mode'], args.allow_effects, args.auth_file)
                state.mkdir(parents=True, exist_ok=True)
                with tempfile.TemporaryDirectory(prefix='.read-', dir=state) as tmp:
                    scratch = Path(tmp)
                    from .records import inventory
                    inputs = inventory(root, provider_input_paths(args.profile, target))
                    stage_inventory(root, scratch / 'inputs', inputs)
                    stage_inventory(safe_path(root, profile['runtime']['path']), scratch / 'runtime', runtime['files'])
                    provider.bind_stage(scratch / 'inputs', scratch / 'runtime', inputs, runtime['files'])
                    seal_stage(scratch / 'inputs')
                    seal_stage(scratch / 'runtime')
                    path = download_snapshot(provider, identity, state / 'downloads')
                    result = {'snapshot': path.relative_to(root).as_posix(), 'manifest': validate_snapshot(path)}
        else:
            if not args.receipt:
                raise ValueError('verify requires an attempt receipt')
            receipt_path = safe_path(root, args.receipt)
            receipt = read_json(receipt_path)
            plan = read_json(receipt_path.parent / 'plan.json')
            if runtime != plan['payload']['runtime']:
                raise ValueError('executing runtime differs from reviewed plan')
            if record_digest(plan['payload']) != plan['digest'] or plan['digest'] != receipt['digest'] or receipt['target'] != identity:
                raise ValueError('verification receipt/target/digest differs')
            if args.dry_run:
                print(json.dumps({'status': 'dry-run', 'digest': receipt['digest'], 'effects': []}))
                return 0
            provider = CommandProvider.from_plan(plan, args.allow_effects, args.auth_file)
            verify_inventory(receipt_path.parent / 'inputs', plan['payload']['inputs'], exact=True)
            verify_inventory(receipt_path.parent / 'runtime', plan['payload']['runtime']['files'], exact=True)
            provider.bind_stage(receipt_path.parent / 'inputs', receipt_path.parent / 'runtime',
                                plan['payload']['inputs'], plan['payload']['runtime']['files'])
            seal_stage(receipt_path.parent / 'inputs')
            seal_stage(receipt_path.parent / 'runtime')
            report = provider.readback(plan, receipt.get('provider_result', {}))
            if readback_matches(plan['payload'], report, receipt.get('provider_result', {})):
                receipt['status'] = 'verified'
                write_record(receipt_path, receipt)
            result = receipt
        print(json.dumps(result, sort_keys=True, ensure_ascii=False))
        return 0
    except (ValueError, OSError, KeyError, TypeError) as error:
        print(f'FAIL: {error}', file=sys.stderr)
        return 1
