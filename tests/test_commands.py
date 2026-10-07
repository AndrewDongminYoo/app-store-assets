import json
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
