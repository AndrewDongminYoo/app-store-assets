"""Verify the complete runtime before a consumer imports or executes it."""
import os
import re
import subprocess
import sys
from pathlib import Path

from .records import file_digest, inventory


def git(root, *args):
    # Do not inherit credential helpers, fsmonitor hooks or personal Git config.
    env = {'PATH': os.defpath + os.pathsep + os.environ.get('PATH', ''),
           'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': os.devnull, 'GIT_OPTIONAL_LOCKS': '0'}
    command = ['git', '-c', 'core.fsmonitor=false', '-c', 'core.hooksPath=' + os.devnull, '-C', str(root), *args]
    result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=30)
    if result.returncode:
        raise ValueError('runtime Git identity cannot be read')
    return result.stdout.strip()


def runtime_inventory(root):
    root = Path(root).resolve()
    if (root / '__pycache__').exists() or any(p.suffix == '.pyc' for p in root.iterdir()):
        raise ValueError('runtime contains unbound root bytecode cache')
    paths = [p.name for p in root.iterdir() if p.is_file() and p.suffix in ('.py', '.rb', '.sh')]
    paths += [name for name in ('app_store_assets', 'lib', 'schemas', 'catalog') if (root / name).exists()]
    for name in paths:
        p = root / name
        if p.is_dir() and any(e.suffix == '.pyc' or e.name == '__pycache__' for e in p.rglob('*')):
            raise ValueError('runtime contains unbound bytecode cache; remove it before verification')
    if 'assets.py' not in paths:
        raise ValueError('runtime CLI is missing')
    return inventory(root, paths)


def runtime_identity(root, pin):
    if set(pin) != {'path', 'url', 'commit', 'files'} or not re.fullmatch(r'[0-9a-f]{40}', pin['commit']):
        raise ValueError('runtime requires an exact URL/commit/inventory pin')
    root = Path(root).resolve()
    if git(root, 'rev-parse', 'HEAD') != pin['commit']:
        raise ValueError('runtime commit differs from approval')
    if git(root, 'remote', 'get-url', 'origin') != pin['url']:
        raise ValueError('runtime source URL differs from approval')
    if git(root, 'status', '--porcelain', '--untracked-files=all'):
        raise ValueError('runtime checkout is modified or contains untracked inputs')
    actual = runtime_inventory(root)
    if actual != pin['files']:
        raise ValueError('runtime inventory/hash differs from approval')
    return {'url': pin['url'], 'commit': pin['commit'], 'files': actual}


def verify_executing_runtime(runtime):
    if runtime_inventory(Path(__file__).resolve().parents[1]) != runtime['files']:
        raise ValueError('executing runtime differs from reviewed plan')


def python_identity():
    return {'version': sys.version, 'binary_sha256': file_digest(Path(sys.executable).resolve())}
