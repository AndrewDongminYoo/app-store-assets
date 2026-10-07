"""Offline plans bind the complete executor, target and transitive inputs."""
from pathlib import Path

from .identity import python_identity, runtime_identity
from .commands import executable_identity
from .catalog import CATALOG_FILE, validate_fields, validate_images
from .profiles import exact_keys, load_profile, target_identity
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
    paths = [profile_path, *target['inputs'], *target['provider'].get('inputs', [])]
    if target['provider'].get('gemfile'):
        paths += [target['provider']['gemfile'], target['provider']['gemfile'] + '.lock']
    if 'version_source' in target:
        paths.append(target['version_source']['file'])
    artifact = None
    if operation == 'binary':
        artifact = artifact_record(root, profile, target)
        paths += list(target['artifact'].values())
    listing = None
    if target.get('metadata'):
        paths.append(target['metadata'])
        listing = read_json(safe_path(root, target['metadata']))
        for key in ('store', 'platform', 'account', 'app_id', 'flavor', 'stage', 'version'):
            if listing.get('target', {}).get(key) != target[key]:
                raise ValueError(f'metadata target/version differs: {key}')
        validate_fields(listing.get('fields', {}), target['store'])
        if operation == 'images':
            entries = [dict(item, locale=locale, slot=slot) for locale, groups in listing.get('images', {}).items()
                       for slot, images in groups.items() for item in images]
            if not entries:
                raise ValueError('empty image listing')
            validated = validate_images(root, entries, target['store'])
            paths += [item['file'] for item in validated]
    remote = None
    if target.get('remote'):
        paths.append(target['remote'])
        remote = read_json(safe_path(root, target['remote']))
        if remote.get('type') == 'snapshot':
            remote = validate_snapshot(safe_path(root, target['remote']).parent)['record']
        if remote.get('target') != target_identity(target):
            raise ValueError('remote snapshot target differs')
    notes = {}
    if operation == 'binary':
        for locale, path in target.get('changelogs', {}).items():
            notes[locale] = safe_path(root, path).read_text()
            paths.append(path)
    effects = ['upload-' + operation]
    if notes:
        effects.append('release-notes')
    if target['store'] == 'google' and operation in ('metadata', 'images'):
        effects.append('shared-listing-across-tracks')
    payload = {'schema_version': 1, 'type': 'release-plan', 'profile': profile_path, 'target_name': target_name,
               'mode': profile['mode'], 'target': target_identity(target), 'operation': operation,
               'effects': effects, 'runtime': runtime, 'runtime_path': profile['runtime']['path'],
               'python': python_identity(), 'input_paths': sorted(set(paths)), 'inputs': inventory(root, paths),
               'catalog_sha256': file_digest(CATALOG_FILE),
               'artifact': target.get('artifact') if artifact else None, 'build': artifact,
               'listing': listing, 'remote': remote, 'release_notes': notes,
               'replacement': target.get('replacement'), 'release_status': target.get('release_status'),
               'provider': target['provider']}
    payload['provider_executable'] = executable_identity(target['provider']['argv'])
    return {'payload': payload, 'digest': record_digest(payload)}


def verify_plan(root, plan):
    if set(plan) != {'payload', 'digest'} or record_digest(plan['payload']) != plan['digest']:
        raise ValueError('plan digest differs from its contents')
    payload = plan['payload']
    current = make_plan(root, payload['profile'], payload['target_name'], payload['operation'])
    if current != plan:
        raise ValueError('approved inputs or target changed; plan differs')
