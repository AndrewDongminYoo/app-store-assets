"""Strict public configuration and explicit application/target identities."""
import re
from pathlib import PurePosixPath

from .records import read_json, safe_path
from .commands import validate_adapter_argv

TOP_KEYS = {'schema_version', 'project', 'mode', 'runtime', 'targets', 'recipes', 'builds'}
TARGET_KEYS = {'store', 'platform', 'account', 'app_id', 'flavor', 'stage', 'version', 'version_source',
               'inputs', 'artifact', 'metadata', 'remote', 'track', 'release_status', 'replacement',
               'provider', 'changelogs', 'assets', 'build', 'recipe', 'account_id'}
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
    if target.get('account_id'):
        result['account_id'] = target['account_id']
    return result


def provider_input_paths(profile_path, target):
    paths = [profile_path, *target['inputs'], *target['provider'].get('inputs', [])]
    if target['provider'].get('gemfile'):
        paths += [target['provider']['gemfile'], target['provider']['gemfile'] + '.lock']
    return paths


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
        derived = dict(zip(('name', 'build'), matches[0], strict=True))
        if 'version' in target and target['version'] != derived:
            raise ValueError('configured version differs from version source')
        target['version'] = derived
    exact_keys(target.get('version'), {'name', 'build'}, ('name', 'build'))
    version = target['version']
    if (not isinstance(version['name'], str) or not re.fullmatch(r'[0-9]+(?:\.[0-9]+){0,3}', version['name'])
            or not isinstance(version['build'], str) or not re.fullmatch(r'[0-9]+', version['build'])):
        raise ValueError('version requires explicit numeric name/build strings')
    for key in IDENTITY_KEYS[:-1]:
        if not isinstance(target[key], str) or not target[key] or any(ord(c) < 32 for c in target[key]):
            raise ValueError(f'invalid target {key}')
    if not re.fullmatch(r'[A-Za-z0-9_.-]+', target['app_id']):
        raise ValueError('invalid app identifier')
    expected_platform = {'apple': ('ios', 'macos'), 'google': ('android',), 'firebase': ('android', 'ios'),
                         'steam': ('windows', 'linux', 'macos'), 'toss': ('web',)}
    if target['store'] not in expected_platform or target['platform'] not in expected_platform[target['store']]:
        raise ValueError('store/platform mismatch')
    if target['store'] == 'google' and (target.get('release_status') not in ('draft', 'completed')
                                       or not target.get('track')):
        raise ValueError('Google requires explicit track and release_status')
    if target['store'] == 'google':
        for name in target.get('changelogs', {}).values():
            path = PurePosixPath(name)
            if 'changelogs' in path.parts and path.name != version['build'] + '.txt':
                raise ValueError('version-named Google changelog differs from target build')
    if not isinstance(target['inputs'], list) or not target['inputs']:
        raise ValueError('declared input inventory is required')
    exact_keys(target['provider'], {'kind', 'argv', 'inputs', 'gemfile'}, ('kind', 'argv'))
    if target['provider']['kind'] != 'command' or not isinstance(target['provider']['argv'], list):
        raise ValueError('provider requires an explicit command adapter')
    validate_adapter_argv(target['provider']['argv'], source_root=root)
    return profile, target
