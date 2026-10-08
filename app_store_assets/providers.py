"""Explicit provider effects; no authentication or automatic backend fallback."""
from pathlib import Path

from .commands import capture_provider_argv, executable_identity, expand_argv, run_command
from .records import file_digest, safe_path, verify_inventory
from .metadata import normalize_remote


CAPABILITIES = {
    'apple': {'local_rules': True, 'command_protocol': True, 'native_backend': 'fastlane-2.240.1'},
    'google': {'local_rules': True, 'command_protocol': True, 'native_backend': 'fastlane-2.240.1'},
    'firebase': {'local_rules': False, 'command_protocol': True, 'native_backend': None},
    'steam': {'local_rules': False, 'command_protocol': True, 'native_backend': None},
    'toss': {'local_rules': False, 'command_protocol': True, 'native_backend': None},
}


class CommandProvider:
    def __init__(self, target, mode, allow_effects=False, auth_file=None, expected_executable=None):
        if not allow_effects:
            raise ValueError('provider effects require explicit authority')
        if mode == 'live' and (not target.get('account_id') or not auth_file):
            raise ValueError('live provider requires explicit account identity and protected auth input')
        self.target = target
        self.mode = mode
        self.auth_file = str(Path(auth_file).resolve()) if auth_file else None
        self.expected = expected_executable or executable_identity(target['provider']['argv'])
        self.root = self.runtime = None

    def bind_stage(self, root, runtime, inputs=None, runtime_files=None):
        self.root, self.runtime = Path(root), Path(runtime)
        approved = {}
        for tree, files in ((self.root, inputs), (self.runtime, runtime_files)):
            if files is not None:
                verify_inventory(tree, files, exact=True)
                approved.update({str(safe_path(tree, name)): digest for name, digest in files.items()})
            else:
                approved.update({str(path): file_digest(path) for path in tree.rglob('*') if path.is_file()})
        argv = expand_argv(self.target['provider']['argv'], self.root, self.runtime)
        gemfile = str(safe_path(self.root, self.target['provider']['gemfile'])) if self.target['provider'].get('gemfile') else None
        self.captured_argv = capture_provider_argv(argv, approved, roots=[self.root, self.runtime], gemfile=gemfile)

    def request(self, action, **values):
        if self.root is None:
            raise ValueError('provider must be bound to immutable staged inputs')
        descriptor = self.target['provider']
        argv = self.captured_argv
        request = {'schema_version': 1, 'action': action, 'root': str(self.root), 'runtime': str(self.runtime),
                   'mode': self.mode, 'authorized': True, 'auth_file': self.auth_file, **values}
        tool_env = {}
        if descriptor.get('gemfile'):
            tool_env['BUNDLE_GEMFILE'] = str(safe_path(self.root, descriptor['gemfile']))
        return run_command(argv, request, self.root, self.root.parent / 'provider-home',
                           expected=self.expected, tool_env=tool_env)

    def snapshot(self, target):
        result = self.request('snapshot', target=target)
        return normalize_remote(result, target) if self.mode == 'live' else result

    def upload(self, plan, staged_root):
        return self.request('upload', target=plan['payload']['target'], plan=plan)

    def readback(self, plan, result):
        return self.request('readback', target=plan['payload']['target'], plan=plan, result=result)

    def download(self, target, output):
        return self.request('download', target=target, output=str(output))
