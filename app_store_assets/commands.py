"""Bound argv adapters with private environments and a small JSON protocol."""
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import struct
from pathlib import Path, PurePosixPath

from .environment import local_environment
from .records import canonical, file_digest
from .provider_python import BOOTSTRAP as PYTHON_BOOTSTRAP
from .provider_ruby import BOOTSTRAP as RUBY_BOOTSTRAP


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


class CapturedArgv(list):
    """Keep the anonymous capture alive until all provider requests finish."""

    def __init__(self, argv, capture):
        super().__init__(argv)
        self.capture = capture

    def __del__(self):
        self.capture.close()


def capture_provider_argv(argv, approved_files, roots=None, gemfile=None):
    """Capture the supported executable closure, never reopen staged code."""
    approved_files = dict(approved_files)
    for name, digest in list(approved_files.items()):
        resolved = str(Path(name).resolve())
        if resolved in approved_files and approved_files[resolved] != digest:
            raise ValueError('conflicting captured source path aliases')
        approved_files[resolved] = digest
    scripts = [(index, arg) for index, arg in enumerate(argv[1:], 1) if arg in approved_files]
    if len(scripts) != 1:
        raise ValueError('provider requires one staged Python/Ruby entrypoint; unbound loaders are unsupported')
    index, path = scripts[0]
    executable = Path(executable_identity(argv)['path']).name
    prefix = argv[1:index]
    requires = []
    if executable.startswith('python'):
        if any(arg not in ('-I', '-S', '-B', '-u') for arg in prefix):
            raise ValueError('unsupported Python provider startup options')
        bootstrap = PYTHON_BOOTSTRAP
        startup = ['-I', '-S', '-B', *(['-u'] if '-u' in prefix else []), '-c']
    elif executable.startswith('ruby'):
        if len(prefix) % 2 or any(prefix[i] != '-r' or not re.fullmatch(r'[A-Za-z0-9_/]+', prefix[i + 1])
                                  or prefix[i + 1].startswith('/') or '..' in prefix[i + 1].split('/')
                                  for i in range(0, len(prefix), 2)):
            raise ValueError('unsupported Ruby provider startup options')
        requires = prefix[1::2]
        if 'bundler/setup' in requires and gemfile is None:
            raise ValueError('Bundler startup requires a declared captured Gemfile and lockfile')
        bootstrap = RUBY_BOOTSTRAP
        startup = ['-e']
    else:
        raise ValueError('staged providers require an installed Python/Ruby interpreter')
    if Path(path).suffix not in ('.py', '.rb'):
        raise ValueError('provider entrypoint must be Python/Ruby source')
    if gemfile and (gemfile not in approved_files or gemfile + '.lock' not in approved_files):
        raise ValueError('Gemfile and lockfile must belong to the approved captured inventory')
    roots = [str(Path(root).absolute()) for root in (roots or [str(Path(path).parent)])]
    roots = sorted(set(roots + [str(Path(root).resolve()) for root in roots]))
    capture = tempfile.TemporaryFile()
    try:
        # One anonymous archive holds all reviewed bytes, not an extension heuristic.
        # A bounded header indexes file slices; payloads are copied incrementally.
        header_bound = 1024 * 1024
        capture.seek(header_bound)
        files, resolved_files = {}, {}
        for name, digest in approved_files.items():
            resolved = str(Path(name).resolve())
            if resolved in resolved_files:
                files[name] = resolved_files[resolved]
                continue
            handle = os.open(name, os.O_RDONLY | os.O_NOFOLLOW)
            offset, count = capture.tell(), 0
            observed = hashlib.sha256()
            with os.fdopen(handle, 'rb') as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b''):
                    observed.update(block)
                    capture.write(block)
                    count += len(block)
            if name == path and count > 65536:
                raise ValueError('provider entrypoint exceeds captured code bound')
            if observed.hexdigest() != digest:
                raise ValueError('provider source differs from approved captured bytes')
            files[name] = resolved_files[resolved] = {'offset': offset, 'size': count}
        if files[path]['size'] > 65536:
            raise ValueError('provider entrypoint exceeds captured code bound')
        directories = {}
        for name in approved_files:
            for directory in Path(name).parents:
                if not any(str(directory) == root or str(directory).startswith(root + os.sep) for root in roots):
                    break
                info = directory.stat()
                directories[str(info.st_dev) + ':' + str(info.st_ino)] = str(directory.resolve())
        header = canonical({'files': files, 'roots': roots, 'entry': path, 'directories': directories,
                            'gemfile': gemfile, 'requires': requires})
        if len(header) + 8 > header_bound:
            raise ValueError('provider captured inventory exceeds header bound')
        capture.seek(0)
        capture.write(struct.pack('>Q', len(header)) + header)
        capture.flush()
        # The child inherits only a read-only descriptor with no filesystem pathname.
        readonly = os.fdopen(os.open('/dev/fd/' + str(capture.fileno()), os.O_RDONLY), 'rb')
        capture.close()
        return CapturedArgv([argv[0], *startup, bootstrap, str(readonly.fileno()), *argv[index + 1:]], readonly)
    except BaseException:
        capture.close()
        raise



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
    inherited = ()
    if isinstance(argv, CapturedArgv):
        argv.capture.seek(0)
        inherited = (argv.capture.fileno(),)
    process = subprocess.run([identity['path'], *argv[1:]], input=canonical(request), cwd=cwd,
                             env=env, capture_output=True, timeout=1200, pass_fds=inherited)
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
