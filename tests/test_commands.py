import os
import sys
import unittest
from unittest.mock import patch

from pipeline_support import fixture, module


class CommandTests(unittest.TestCase):
    def setUp(self):
        self.commands = module(self, 'commands')
        self.root, self.profile = fixture(self)

    def test_local_adapter_does_not_inherit_authentication_or_shell_expansion(self):
        script = self.root / 'helpers/inspect.py'
        script.write_text('''import json,os,sys
request=json.load(sys.stdin)
assert not any(k in os.environ for k in ('FASTLANE_SESSION','GOOGLE_APPLICATION_CREDENTIALS','SUPPLY_TRACK'))
print(json.dumps({'argument':sys.argv[1], 'target':request['target']}))
''')
        with patch.dict(os.environ, {'FASTLANE_SESSION': 'fake-secret', 'GOOGLE_APPLICATION_CREDENTIALS': '/fake.json',
                                    'SUPPLY_TRACK': 'production'}):
            result = self.commands.run_command([sys.executable, str(script), 'literal $(touch sentinel)'],
                                              {'target': 'approved'}, self.root, self.root / 'home')
        self.assertEqual(result, {'argument': 'literal $(touch sentinel)', 'target': 'approved'})
        self.assertFalse((self.root / 'sentinel').exists())

    def test_bound_python_entrypoint_executes_captured_bytes_after_path_replacement(self):
        provider = module(self, 'providers').CommandProvider(
            self.profile['targets']['production'], 'fixture', allow_effects=True)
        script = self.root / 'helpers/provider.py'
        script.write_text('import json,sys; print(json.dumps({"code":"approved", "file":__file__, "arg":sys.argv[1]}))\n')
        provider.target['provider']['argv'].append('literal $(touch sentinel)')
        provider.bind_stage(self.root, self.root / 'tools/app-store-assets')
        script.write_text('import json; print(json.dumps({"code":"unreviewed"}))\n')
        result = provider.request('snapshot')
        self.assertEqual(result, {'code': 'approved', 'file': str(script), 'arg': 'literal $(touch sentinel)'})
        self.assertFalse((self.root / 'sentinel').exists())

    def test_bound_ruby_entrypoint_preserves_file_main_guard_and_stdin(self):
        target = self.profile['targets']['production']
        target['provider']['argv'] = ['ruby', '{root}/helpers/provider.rb', 'literal argument']
        script = self.root / 'helpers/provider.rb'
        script.write_text('require "json"; if $PROGRAM_NAME == __FILE__; puts JSON.generate({code:"approved", file:__FILE__, arg:ARGV[0], action:JSON.parse(STDIN.read)["action"]}); end\n')
        provider = module(self, 'providers').CommandProvider(target, 'fixture', allow_effects=True)
        provider.bind_stage(self.root, self.root / 'tools/app-store-assets')
        script.write_text('require "json"; puts JSON.generate({code:"unreviewed"})\n')
        self.assertEqual(provider.request('snapshot'), {'code': 'approved', 'file': str(script),
                                                       'arg': 'literal argument', 'action': 'snapshot'})

    def test_capture_rejects_changed_bytes_and_unsupported_loaders(self):
        script = self.root / 'helpers/provider.py'
        script.write_text('print("approved")\n')
        files = {str(script): module(self, 'records').file_digest(script)}
        script.write_text('print("unreviewed")\n')
        with self.assertRaisesRegex(ValueError, 'approved captured bytes'):
            self.commands.capture_provider_argv([sys.executable, str(script)], files)
        with self.assertRaisesRegex(ValueError, 'Python/Ruby'):
            self.commands.capture_provider_argv(['/bin/sh', str(script)], files)
        with self.assertRaisesRegex(ValueError, 'startup options'):
            self.commands.capture_provider_argv([sys.executable, '-c', str(script)], files)

    def test_adapter_failure_never_echoes_raw_stderr_or_private_response(self):
        script = self.root / 'helpers/fail.py'
        script.write_text('import sys; print("fake-token-private",file=sys.stderr);sys.exit(1)\n')
        with self.assertRaises(ValueError) as error:
            self.commands.run_command([sys.executable, str(script)], {}, self.root, self.root / 'home')
        self.assertNotIn('fake-token-private', str(error.exception))

    def test_remote_command_requires_explicit_authority_and_account_binding(self):
        providers = module(self, 'providers')
        target = self.profile['targets']['production']
        with self.assertRaisesRegex(ValueError, 'authority|effects'):
            providers.CommandProvider(target, 'fixture', allow_effects=False)
        with self.assertRaisesRegex(ValueError, 'account|auth'):
            providers.CommandProvider(target, 'live', allow_effects=True)


if __name__ == '__main__':
    unittest.main()
