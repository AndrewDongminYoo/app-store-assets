#!/usr/bin/env python3
"""Copy to scripts/store_assets/bootstrap.py; invoke with Python -I -S."""
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]


def safe(root, name):
    if not isinstance(name, str) or not name or '\\' in name or any(ord(c) < 32 for c in name):
        raise ValueError('invalid dependency path')
    path = PurePosixPath(name)
    if path.is_absolute() or '..' in path.parts or str(path) != name or name == '.':
        raise ValueError('dependency path must be canonical and relative')
    result = root
    for part in path.parts:
        result = result / part
        if result.is_symlink():
            raise ValueError('runtime symlink is forbidden')
    return result


def unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate profile key')
        result[key] = value
    return result


def verify():
    for key in ('APP_STORE_ASSETS_ROOT', 'STORE_UPLOAD_TOOL'):
        if key in os.environ:
            raise ValueError('runtime override is forbidden: ' + key)
    profile_path = safe(ROOT, 'store-upload.json')
    if profile_path.stat().st_size > 8 * 1024 * 1024:
        raise ValueError('profile exceeds size bound')
    profile = json.loads(profile_path.read_text(), object_pairs_hook=unique)
    pin = profile['runtime']
    if set(pin) != {'path', 'url', 'commit', 'files'} or not re.fullmatch('[0-9a-f]{40}', pin['commit']):
        raise ValueError('runtime requires full URL/commit/inventory pin')
    runtime = safe(ROOT, pin['path'])
    env = {'PATH': os.defpath + os.pathsep + os.environ.get('PATH', ''), 'GIT_CONFIG_GLOBAL': os.devnull,
           'GIT_CONFIG_NOSYSTEM': '1', 'GIT_OPTIONAL_LOCKS': '0'}
    def git(*args):
        result = subprocess.run(['git', '-c', 'core.fsmonitor=false', '-c', 'core.hooksPath=' + os.devnull,
                                 '-C', str(runtime), *args], env=env, capture_output=True, text=True, timeout=30)
        if result.returncode:
            raise ValueError('runtime Git identity unavailable; initialize the declared submodule')
        return result.stdout.strip()
    if git('rev-parse', 'HEAD') != pin['commit'] or git('remote', 'get-url', 'origin') != pin['url']:
        raise ValueError('runtime URL/commit differs from approval')
    if git('status', '--porcelain', '--untracked-files=all'):
        raise ValueError('runtime checkout is modified')
    files = [p for p in runtime.iterdir() if p.is_file() and p.suffix in ('.py', '.rb', '.sh')]
    for directory in ('app_store_assets', 'lib', 'schemas', 'catalog'):
        folder = safe(runtime, directory)
        if folder.exists():
            files += list(folder.rglob('*'))
    if (runtime / '__pycache__').exists() or any(p.name == '__pycache__' or p.suffix == '.pyc' for p in files):
        raise ValueError('runtime bytecode cache is forbidden')
    actual = {}
    for path in files:
        name = path.relative_to(runtime).as_posix()
        safe(runtime, name)
        if path.is_file():
            actual[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    if 'assets.py' not in actual or actual != pin['files']:
        raise ValueError('runtime inventory/hash differs from approval')
    return runtime


def main():
    try:
        if any(arg in ('--root', '--profile') or arg.startswith(('--root=', '--profile=')) for arg in sys.argv[1:]):
            raise ValueError('consumer root/profile overrides are forbidden')
        runtime = verify()
        sys.path.insert(0, str(runtime))
        from app_store_assets.cli import main as run
        return run([*sys.argv[1:], '--root', str(ROOT), '--profile', 'store-upload.json'])
    except (ValueError, OSError, KeyError, TypeError) as error:
        print('FAIL: ' + str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
