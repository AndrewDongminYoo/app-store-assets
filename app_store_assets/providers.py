"""Explicit provider effects; no authentication or automatic backend fallback."""
from copy import deepcopy
from pathlib import Path

from .commands import capture_provider_argv, executable_identity, expand_argv, run_command
from .records import file_digest, safe_path, verify_inventory
from .metadata import normalize_remote
from .profiles import target_identity
from .identity import verify_executing_runtime


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
        self.target = deepcopy(target)
        self.mode = mode
        self.auth_file = str(Path(auth_file).resolve()) if auth_file else None
        self.expected = deepcopy(expected_executable or executable_identity(target['provider']['argv']))
        self.reviewed_binding = None
        self.root = self.runtime = None

    @classmethod
    def from_plan(cls, plan, allow_effects=False, auth_file=None):
        """Select authority and adapter exclusively from the reviewed payload."""
        payload = plan['payload']
        verify_executing_runtime(payload['runtime'])
        target = dict(payload['target'], provider=payload['provider'])
        provider = cls(target, payload['mode'], allow_effects, auth_file, payload['provider_executable'])
        provider.verify_plan_binding(payload)
        return provider

    def verify_plan_binding(self, payload):
        """Reject a stale object before staging or authenticated invocation."""
        expected = {key: payload[key] for key in ('target', 'mode', 'provider', 'provider_executable')}
        current = {'target': target_identity(self.target), 'mode': self.mode,
                   'provider': self.target['provider'], 'provider_executable': self.expected}
        if current != expected:
            raise ValueError('provider configuration differs from reviewed plan')
        self.reviewed_binding = deepcopy(expected)

    def bind_stage(self, root, runtime, inputs=None, runtime_files=None):
        self.root, self.runtime = Path(root), Path(runtime)
        self.bound_binding = deepcopy(self.reviewed_binding or {
            'mode': self.mode, 'provider': self.target['provider'], 'provider_executable': self.expected})
        descriptor = self.bound_binding['provider']
        approved = {}
        for tree, files in ((self.root, inputs), (self.runtime, runtime_files)):
            if files is not None:
                verify_inventory(tree, files, exact=True)
                approved.update({str(safe_path(tree, name)): digest for name, digest in files.items()})
            else:
                approved.update({str(path): file_digest(path) for path in tree.rglob('*') if path.is_file()})
        argv = expand_argv(descriptor['argv'], self.root, self.runtime)
        gemfile = str(safe_path(self.root, descriptor['gemfile'])) if descriptor.get('gemfile') else None
        self.captured_argv = capture_provider_argv(argv, approved, roots=[self.root, self.runtime], gemfile=gemfile)

    def request(self, action, **values):
        if self.root is None:
            raise ValueError('provider must be bound to immutable staged inputs')
        descriptor = self.bound_binding['provider']
        if 'target' in self.bound_binding and values.get('target') != self.bound_binding['target']:
            raise ValueError('provider request target differs from reviewed plan')
        argv = self.captured_argv
        request = {'schema_version': 1, 'action': action, 'root': str(self.root), 'runtime': str(self.runtime),
                   'mode': self.bound_binding['mode'], 'authorized': True, 'auth_file': self.auth_file, **values}
        tool_env = {}
        if descriptor.get('gemfile'):
            tool_env['BUNDLE_GEMFILE'] = str(safe_path(self.root, descriptor['gemfile']))
        return run_command(argv, request, self.root, self.root.parent / 'provider-home',
                           expected=self.bound_binding['provider_executable'], tool_env=tool_env)

    def snapshot(self, target):
        result = self.request('snapshot', target=target)
        return normalize_remote(result, target) if self.bound_binding['mode'] == 'live' else result

    def upload(self, plan, staged_root):
        return self.request('upload', target=plan['payload']['target'], plan=plan)

    def readback(self, plan, result):
        return self.request('readback', target=plan['payload']['target'], plan=plan, result=result)

    def download(self, target, output):
        return self.request('download', target=target, output=str(output))
