"""Strict public configuration and explicit application/target identities."""
import re

from .records import read_json, safe_path

TOP_KEYS = {'schema_version', 'project', 'mode', 'runtime', 'targets', 'recipes', 'builds'}
TARGET_KEYS = {'store', 'platform', 'account', 'app_id', 'flavor', 'stage', 'version', 'version_source',
               'inputs', 'artifact', 'metadata', 'remote', 'track', 'release_status', 'replacement',
               'provider', 'changelogs', 'assets', 'build', 'recipe'}
IDENTITY_KEYS = ('store', 'platform', 'account', 'app_id', 'flavor', 'stage', 'version')


def exact_keys(value, allowed, required=()):
    if not isinstance(value, dict) or set(value) - set(allowed):
        raise ValueError('unknown configuration key or invalid object')
    if set(required) - set(value):
        raise ValueError('missing required configuration key')


def target_identity(target):
    result = {key: target[key] for key in IDENTITY_KEYS}
    if target['store'] == 'google':
        result['track'] = target['track']
    return result


def load_profile(root, path, name):
    profile = read_json(safe_path(root, path))
    exact_keys(profile, TOP_KEYS, ('schema_version', 'project', 'mode', 'runtime', 'targets'))
    if profile['schema_version'] != 1 or profile['mode'] not in ('fixture', 'live'):
        raise ValueError('unsupported profile schema or mode')
    if name not in profile['targets']:
        raise ValueError('unknown target')
    target = dict(profile['targets'][name])
    exact_keys(target, TARGET_KEYS, IDENTITY_KEYS[:-1] + ('inputs', 'provider'))
    if 'version_source' in target:
        exact_keys(target['version_source'], {'file'}, ('file',))
        version_file = safe_path(root, target['version_source']['file'])
        matches = re.findall(r'^version:\s*([^\s+]+)\+([0-9]+)\s*$', version_file.read_text(), re.MULTILINE)
        if len(matches) != 1:
            raise ValueError('version source must contain one exact pubspec version')
        derived = dict(zip(('name', 'build'), matches[0]))
        if 'version' in target and target['version'] != derived:
            raise ValueError('configured version differs from version source')
        target['version'] = derived
    exact_keys(target.get('version'), {'name', 'build'}, ('name', 'build'))
    for key in IDENTITY_KEYS[:-1]:
        if not isinstance(target[key], str) or not target[key] or any(ord(c) < 32 for c in target[key]):
            raise ValueError(f'invalid target {key}')
    if not re.fullmatch(r'[A-Za-z0-9_.-]+', target['app_id']):
        raise ValueError('invalid app identifier')
    expected_platform = {'apple': ('ios', 'macos'), 'google': ('android',), 'firebase': ('android', 'ios'),
                         'steam': ('windows', 'linux', 'macos'), 'toss': ('web',)}
    if target['store'] not in expected_platform or target['platform'] not in expected_platform[target['store']]:
        raise ValueError('store/platform mismatch')
    if target['store'] == 'google' and (target.get('release_status') not in ('draft', 'completed', 'inProgress', 'halted')
                                       or not target.get('track')):
        raise ValueError('Google requires explicit track and release_status')
    if not isinstance(target['inputs'], list) or not target['inputs']:
        raise ValueError('declared input inventory is required')
    exact_keys(target['provider'], {'kind', 'argv', 'inputs'}, ('kind', 'argv'))
    if target['provider']['kind'] != 'command' or not isinstance(target['provider']['argv'], list):
        raise ValueError('provider requires an explicit command adapter')
    return profile, target
