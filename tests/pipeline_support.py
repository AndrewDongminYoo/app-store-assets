"""Synthetic contracts only; fixture repositories contain no personal assets."""
import hashlib
import importlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def module(test, name):
    try:
        return importlib.import_module('app_store_assets.' + name)
    except ModuleNotFoundError as error:
        test.fail(f'Missing planned runtime interface: {error.name}')


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, sort_keys=True) + '\n')


def git(root, *args):
    env = dict(os.environ, GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL='/dev/null', GIT_OPTIONAL_LOCKS='0')
    return subprocess.check_output(['git', '-c', 'core.hooksPath=/dev/null', '-c',
                                    'user.name=Synthetic fixture', '-c', 'user.email=fixture@example.invalid',
                                    '-C', str(root), *args], env=env, text=True).strip()


def fixture(test, store='apple'):
    tmp = tempfile.TemporaryDirectory(prefix="fixture space $ literal '")
    test.addCleanup(tmp.cleanup)
    root = Path(tmp.name)
    runtime = root / 'tools/app-store-assets'
    shutil.copytree(ROOT, runtime, ignore=shutil.ignore_patterns('.git', '.superpowers', '__pycache__', '*.pyc'))
    git(runtime, 'init', '-q')
    git(runtime, 'add', '.')
    git(runtime, 'commit', '-qm', 'Synthetic pinned runtime')
    git(runtime, 'remote', 'add', 'origin', 'https://example.invalid/app-store-assets.git')
    identity = module(test, 'identity')
    pin = {'path': 'tools/app-store-assets', 'url': 'https://example.invalid/app-store-assets.git',
           'commit': git(runtime, 'rev-parse', 'HEAD'), 'files': identity.runtime_inventory(runtime)}
    (root / 'helpers').mkdir()
    (root / 'helpers/Fastfile').write_text('track = "alpha"\n')
    (root / 'helpers/version_guard.rb').write_text('raise unless version == expected\n')
    (root / 'helpers/provider.py').write_text('# synthetic provider; implemented in CLI tests\n')
    (root / 'metadata/en-US/changelogs').mkdir(parents=True)
    (root / 'metadata/en-US/changelogs/9.txt').write_text('Approved notes\n')
    (root / 'artifacts').mkdir()
    (root / 'artifacts/app.bin').write_bytes(b'approved artifact')
    target = {'store': store, 'platform': 'ios' if store == 'apple' else 'android',
              'account': 'personal', 'app_id': 'com.example.fixture', 'flavor': 'production',
              'stage': 'production', 'version': {'name': '1.0', 'build': '9'},
              'inputs': ['helpers', 'metadata'], 'artifact': {'path': 'artifacts/app.bin', 'record': 'artifact.json'},
              'remote': 'remote.json', 'metadata': 'metadata/listing.json',
              'provider': {'kind': 'command', 'argv': [sys.executable, '{root}/helpers/provider.py']}}
    if store == 'google':
        target.update(track='alpha', release_status='completed')
    listing = {'schema_version': 1, 'type': 'metadata', 'target': {
        k: target[k] for k in ('store', 'platform', 'account', 'app_id', 'flavor', 'stage', 'version')},
        'fields': {'en-US': {'description': 'Approved description'}}, 'images': {}}
    write_json(root / 'metadata/listing.json', listing)
    remote = {'schema_version': 1, 'target': listing['target'], 'revision': 'remote-1',
              'version_id': 'editable-1.0', 'editable': True, 'review_active': False,
              'fields': listing['fields'], 'images': {}}
    if store == 'google': remote['target']['track'] = target['track']
    write_json(root / 'remote.json', remote)
    write_json(root / 'artifact.json', {'schema_version': 1, 'type': 'build',
        'app_id': target['app_id'], 'platform': target['platform'], 'flavor': target['flavor'],
        'version': target['version'], 'sha256': hashlib.sha256(b'approved artifact').hexdigest(),
        'evidence': 'fixture'})
    profile = {'schema_version': 1, 'project': 'synthetic', 'mode': 'fixture',
               'runtime': pin, 'targets': {'production': target}}
    write_json(root / 'store-upload.json', profile)
    return root, profile
