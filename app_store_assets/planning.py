"""Offline plans bind the complete executor, target and transitive inputs."""
from pathlib import Path

from .identity import git, python_identity, runtime_identity
from .commands import capture_provider_argv, executable_identity, expand_argv
from .catalog import CATALOG_FILE, rules, validate_fields, validate_images
from .metadata import remote_observation
from .profiles import exact_keys, load_profile, provider_input_paths, target_identity
from .records import file_digest, inventory, read_json, record_digest, safe_path
from .snapshots import validate_snapshot

OPERATIONS = {'binary', 'metadata', 'images'}


def artifact_record(root, profile, target):
    descriptor = target.get('artifact')
    exact_keys(descriptor, {'path', 'record'}, ('path', 'record'))
    record = read_json(safe_path(root, descriptor['record']))
    if record.get('type') == 'snapshot':
        record = validate_snapshot(safe_path(root, descriptor['record']).parent)['record']
    for key in ('app_id', 'platform', 'flavor', 'version'):
        if record.get(key) != target[key]:
            raise ValueError(f'artifact build identity differs: {key}')
    if record.get('type') != 'build' or record.get('schema_version') != 1:
        raise ValueError('unsupported build record')
    if record.get('evidence') not in ('fixture', 'inspected'):
        raise ValueError('artifact build inspection is missing')
    if profile['mode'] != 'fixture' and record.get('evidence') == 'fixture':
        raise ValueError('fixture build cannot be transferred to a live store')
    if profile['mode'] == 'live':
        guards = record.get('native_guards', {})
        if not isinstance(guards, dict) or not guards or any(value is not True for value in guards.values()):
            raise ValueError('artifact native guard evidence is missing or failed')
        if not record.get('source_inputs') or not record.get('source_commit') or not record.get('inspector'):
            raise ValueError('artifact native source/inspection evidence is missing')
        if git(root, 'rev-parse', 'HEAD') != record['source_commit']:
            raise ValueError('artifact source commit differs from current checkout')
        if inventory(root, record['adapter']['inputs']) != record['source_inputs']:
            raise ValueError('artifact source inputs changed since build')
    if file_digest(safe_path(root, descriptor['path'])) != record.get('sha256'):
        raise ValueError('artifact hash differs from build record')
    return record


def make_plan(root, profile_path, target_name, operation):
    root = Path(root).resolve()
    if operation not in OPERATIONS:
        raise ValueError('unsupported operation; submission/promotion is not implicit')
    profile, target = load_profile(root, profile_path, target_name)
    if operation == 'binary' and target['stage'] == 'development':
        raise ValueError('development store binary transfer is blocked')
    runtime = runtime_identity(safe_path(root, profile['runtime']['path']), profile['runtime'])
    paths = provider_input_paths(profile_path, target)
    if 'version_source' in target:
        paths.append(target['version_source']['file'])
    artifact = None
    if operation == 'binary':
        artifact = artifact_record(root, profile, target)
        paths += list(target['artifact'].values())
    listing = None
    assets = None
    if operation in ('metadata', 'images') and not target.get('metadata'):
        raise ValueError('metadata/image operations require a declared listing')
    if target.get('metadata'):
        paths.append(target['metadata'])
        listing = read_json(safe_path(root, target['metadata']))
        if listing.get('target') != target_identity(target):
            raise ValueError('metadata target/account/track/version differs')
        listing['fields'] = validate_fields(listing.get('fields', {}), target['store'])
        if operation == 'images':
            exact_keys(target.get('replacement'), {'locales', 'slots', 'allow_delete'}, ('locales', 'slots', 'allow_delete'))
            policy = target['replacement']
            if type(policy['allow_delete']) is not bool or any(not isinstance(policy[k], list) or not policy[k] for k in ('locales', 'slots')):
                raise ValueError('image replacement requires explicit locale/slot/deletion policy')
            entries = [dict(item, locale=locale, slot=slot) for locale, groups in listing.get('images', {}).items()
                       for slot, images in groups.items() for item in images]
            if not entries:
                raise ValueError('empty image listing')
            validated = validate_images(root, entries, target['store'])
            paths += [item['file'] for item in validated]
            descriptor = target.get('assets')
            if profile['mode'] == 'live' and not descriptor:
                raise ValueError('live images require a selected immutable asset manifest')
            if descriptor:
                exact_keys(descriptor, {'manifest'}, ('manifest',))
                manifest_path = safe_path(root, descriptor['manifest'])
                assets = validate_snapshot(manifest_path.parent)['record']
                if assets.get('type') != 'asset-manifest' or assets.get('target') != target_identity(target):
                    raise ValueError('asset manifest target/version differs')
                if assets.get('provenance', {}).get('status') not in ('widget-rendered', 'unverified-import'):
                    raise ValueError('asset manifest native capture evidence adapter is unsupported')
                prefix = manifest_path.parent.relative_to(root)
                intended = {(str(prefix / item['file']), item['locale'], item['slot'], item['sha256']) for item in assets['assets']}
                actual = {(item['file'], item['locale'], item['slot'], item['sha256']) for item in validated}
                if intended != actual or len(assets['assets']) != len(validated):
                    raise ValueError('asset manifest inventory differs from listing')
                paths.append(descriptor['manifest'])
    remote = None
    if target.get('remote'):
        paths.append(target['remote'])
        remote = read_json(safe_path(root, target['remote']))
        if remote.get('type') == 'snapshot':
            snapshot = safe_path(root, target['remote']).parent
            remote = validate_snapshot(snapshot)['record']
            paths.append(snapshot.relative_to(root).as_posix())
        if remote.get('target') != target_identity(target):
            raise ValueError('remote snapshot target differs')
        remote = remote_observation(remote)
    notes = {}
    if operation == 'binary':
        if target['store'] == 'apple' and target.get('changelogs'):
            raise ValueError('Apple binary localized notes require a separate beta-localization adapter')
        for locale, path in target.get('changelogs', {}).items():
            notes[locale] = safe_path(root, path).read_text()
            if target['store'] == 'google' and len(notes[locale]) > rules()['stores']['google']['release_notes_limit']:
                raise ValueError(f'release-notes limit exceeded: {locale}')
            paths.append(path)
    effects = ['upload-' + operation]
    if notes:
        effects.append('release-notes')
    if target['store'] == 'google' and operation == 'binary':
        effects.append('append-draft-track-release' if target['release_status'] == 'draft' else 'replace-track-releases')
    if target['store'] == 'google' and operation in ('metadata', 'images'):
        effects.append('shared-listing-across-tracks')
    payload = {'schema_version': 1, 'type': 'release-plan', 'profile': profile_path, 'target_name': target_name,
               'mode': profile['mode'], 'target': target_identity(target), 'operation': operation,
               'effects': effects, 'runtime': runtime, 'runtime_path': profile['runtime']['path'],
               'python': python_identity(), 'input_paths': sorted(set(paths)), 'inputs': inventory(root, paths),
               'catalog_sha256': file_digest(CATALOG_FILE),
               'artifact': target.get('artifact') if artifact else None, 'build': artifact,
               'listing': listing, 'assets': assets, 'remote': remote, 'release_notes': notes,
               'replacement': target.get('replacement'), 'release_status': target.get('release_status'),
               'provider': target['provider']}
    payload['provider_executable'] = executable_identity(target['provider']['argv'])
    approved_files = {str(safe_path(root, name)): digest for name, digest in payload['inputs'].items()}
    runtime_root = safe_path(root, profile['runtime']['path'])
    approved_files.update({str(safe_path(runtime_root, name)): digest for name, digest in runtime['files'].items()})
    capture_provider_argv(expand_argv(target['provider']['argv'], root, runtime_root), approved_files)
    return {'payload': payload, 'digest': record_digest(payload)}


def verify_plan(root, plan):
    if set(plan) != {'payload', 'digest'} or record_digest(plan['payload']) != plan['digest']:
        raise ValueError('plan digest differs from its contents')
    payload = plan['payload']
    current = make_plan(root, payload['profile'], payload['target_name'], payload['operation'])
    if current != plan:
        raise ValueError('approved inputs or target changed; plan differs')
