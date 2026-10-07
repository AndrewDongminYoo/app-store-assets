"""Bound argv adapters with private environments and a small JSON protocol."""
import json
import os
import shutil
import subprocess
from pathlib import Path

from .environment import local_environment
from .records import canonical, file_digest


def executable_identity(argv):
    if not isinstance(argv, list) or not argv or any(not isinstance(a, str) or '\x00' in a for a in argv):
        raise ValueError('adapter argv must be a nonempty string array')
    executable = shutil.which(argv[0])
    if not executable:
        raise ValueError('declared adapter tool is unavailable')
    executable = str(Path(executable).resolve())
    return {'path': executable, 'sha256': file_digest(executable)}


def expand_argv(argv, root, runtime=None, output=None):
    values = {'{root}': str(root), '{runtime}': str(runtime), '{output}': str(output)}
    result = []
    for arg in argv:
        for key, value in values.items():
            arg = arg.replace(key, value)
        result.append(arg)
    return result


def run_command(argv, request, cwd, home, expected=None, tool_env=None):
    identity = executable_identity(argv)
    if expected is not None and identity != expected:
        raise ValueError('adapter executable differs from approved tool identity')
    home = Path(home)
    home.mkdir(parents=True, exist_ok=True)
    env = local_environment(home)
    env.update({'FASTLANE_SKIP_UPDATE_CHECK': '1', 'FASTLANE_HIDE_CHANGELOG': '1',
                'FASTLANE_DISABLE_COLORS': '1', 'FASTLANE_OPT_OUT_USAGE': '1',
                'FASTLANE_DONT_STORE_PASSWORD': '1', 'BUNDLE_FROZEN': 'true'})
    if tool_env:
        if set(tool_env) - {'GEM_PATH', 'BUNDLE_GEMFILE'}:
            raise ValueError('unsupported adapter tool environment')
        env.update(tool_env)
    process = subprocess.run([identity['path'], *argv[1:]], input=canonical(request), cwd=cwd,
                             env=env, capture_output=True, timeout=1200)
    if process.returncode:
        raise ValueError('declared adapter failed; private diagnostics were not exported')
    if len(process.stdout) > 8 * 1024 * 1024:
        raise ValueError('adapter response exceeds protocol bound')
    try:
        result = json.loads(process.stdout)
    except (ValueError, UnicodeError):
        raise ValueError('adapter must return one JSON object') from None
    if not isinstance(result, dict):
        raise ValueError('adapter must return one JSON object')
    return result
