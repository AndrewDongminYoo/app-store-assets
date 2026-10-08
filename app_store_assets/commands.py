"""Bound argv adapters with private environments and a small JSON protocol."""
import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path, PurePosixPath

from .environment import local_environment
from .records import canonical, file_digest


def executable_identity(argv):
    if not isinstance(argv, list) or not argv or any(not isinstance(a, str) or '\x00' in a for a in argv):
        raise ValueError('adapter argv must be a nonempty string array')
    executable = shutil.which(argv[0])
    if not executable:
        raise ValueError('declared adapter tool is unavailable')
    executable = str(Path(executable).resolve())
    with Path(executable).open('rb') as stream:
        if stream.read(2) == b'#!':
            raise ValueError('direct script adapters must use an installed interpreter and staged script path')
    return {'path': executable, 'sha256': file_digest(executable)}


def validate_adapter_argv(argv, source_root=None):
    if not isinstance(argv, list) or not argv or any(not isinstance(a, str) or '\x00' in a for a in argv):
        raise ValueError('adapter argv must be a nonempty string array')
    if source_root is not None and Path(executable_identity(argv)['path']).is_relative_to(Path(source_root).resolve()):
        raise ValueError('adapter executable inside source inputs must use a staged script and installed interpreter')
    for arg in argv[1:]:
        path = arg.split('=', 1)[-1] if arg.startswith('-') and '=' in arg else arg
        compact_option = re.fullmatch(r'-[A-Za-z]+(/.*)', path)
        if compact_option:
            path = compact_option.group(1)
        if PurePosixPath(path).is_absolute() or '..' in PurePosixPath(path).parts:
            raise ValueError('adapter paths must remain inside staged trees; use {root}/{runtime}/{output}')
        for marker in ('{root}', '{runtime}', '{output}'):
            if marker in path and not (path == marker or path.startswith(marker + '/')):
                raise ValueError('adapter path placeholder must identify a staged tree')


def expand_argv(argv, root, runtime=None, output=None):
    validate_adapter_argv(argv)
    for marker, path in (('{root}', root), ('{runtime}', runtime), ('{output}', output)):
        if path is None and any(marker in arg for arg in argv):
            raise ValueError('adapter path requires its declared staged tree')
    values = {'{root}': str(root), '{runtime}': str(runtime), '{output}': str(output)}
    result = []
    for arg in argv:
        for key, value in values.items():
            arg = arg.replace(key, value)
        result.append(arg)
    return result


def capture_provider_argv(argv, approved_files):
    """Launch reviewed entrypoint bytes from OS argv, never reopen its pathname."""
    scripts = [(index, arg) for index, arg in enumerate(argv[1:], 1) if arg in approved_files]
    if not scripts:
        # Native installed executables are covered by executable_identity.
        if any(Path(arg).suffix in ('.py', '.rb') for arg in argv[1:]):
            raise ValueError('provider script must belong to the approved staged inventory')
        return argv
    if len(scripts) != 1:
        raise ValueError('provider requires one staged Python/Ruby entrypoint')
    index, path = scripts[0]
    executable = Path(executable_identity(argv)['path']).name
    prefix = argv[1:index]
    if executable.startswith('python'):
        if any(arg not in ('-I', '-S', '-B', '-u') for arg in prefix):
            raise ValueError('unsupported Python provider startup options')
        language = 'python'
    elif executable.startswith('ruby'):
        if len(prefix) % 2 or any(prefix[i] != '-r' or not re.fullmatch(r'[A-Za-z0-9_/]+', prefix[i + 1])
                                  or prefix[i + 1].startswith('/') or '..' in prefix[i + 1].split('/')
                                  for i in range(0, len(prefix), 2)):
            raise ValueError('unsupported Ruby provider startup options')
        language = 'ruby'
    else:
        raise ValueError('staged providers require an installed Python/Ruby interpreter')
    handle = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(handle, 'rb') as stream:
        code = stream.read(65537)
    if len(code) > 65536:
        raise ValueError('provider entrypoint exceeds captured code bound')
    if hashlib.sha256(code).hexdigest() != approved_files[path]:
        raise ValueError('provider entrypoint differs from approved captured bytes')
    encoded = base64.b64encode(code).decode('ascii')
    if language == 'python':
        bootstrap = ('import base64,sys; p=sys.argv.pop(1); code=sys.argv.pop(1); sys.argv[0]=p; '
                     + ('' if '-I' in prefix else 'sys.path[0]=__import__("os").path.dirname(p); ')
                     + 'exec(compile(base64.b64decode(code),p,"exec"),'
                     + '{"__name__":"__main__","__file__":p,"__package__":None,"__builtins__":__builtins__})')
        return [argv[0], *prefix, '-c', bootstrap, path, encoded, *argv[index + 1:]]
    bootstrap = 'p=ARGV.shift; code=ARGV.shift; $0=p; eval(code.unpack1("m0").force_encoding("UTF-8"),TOPLEVEL_BINDING,p)'
    return [argv[0], *prefix, '-e', bootstrap, path, encoded, *argv[index + 1:]]


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
