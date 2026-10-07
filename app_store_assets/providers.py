"""Explicit provider effects; no authentication or automatic backend fallback."""
from pathlib import Path

from .commands import executable_identity, expand_argv, run_command
from .records import safe_path
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

    def bind_stage(self, root, runtime):
        self.root, self.runtime = Path(root), Path(runtime)

    def request(self, action, **values):
        if self.root is None:
            raise ValueError('provider must be bound to immutable staged inputs')
        descriptor = self.target['provider']
        argv = expand_argv(descriptor['argv'], self.root, self.runtime)
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
