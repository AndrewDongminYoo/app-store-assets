import sys
import unittest

from pipeline_support import fixture, module


class BuildTests(unittest.TestCase):
    def setUp(self):
        self.builds = module(self, 'builds')
        self.root, self.profile = fixture(self)

    def test_flutter_and_godot_commands_are_build_only_with_explicit_identity(self):
        version = {'name': '1.2.3', 'build': '42'}
        command = self.builds.flutter_argv('android', 'production', version)
        self.assertEqual(command[:3], ['flutter', 'build', 'appbundle'])
        self.assertEqual(command[command.index('--flavor') + 1], 'production')
        self.assertEqual(command[command.index('--build-number') + 1], '42')
        self.assertNotIn('merry', command)
        self.assertNotIn('fastlane', command)
        godot = self.builds.godot_argv('Godot', 'Android production', 'result.aab', self.root)
        self.assertEqual(godot[-3:], ['--export-release', 'Android production', 'result.aab'])

    def adapter(self, wrong=False):
        script = self.root / 'helpers/build_fixture.py'
        script.write_text('''import json,sys,pathlib
r=json.load(sys.stdin)
p=pathlib.Path(r['output'])/'app.bin'
p.write_bytes(b'new fixture build')
t=r['target']
print(json.dumps({'artifact':'app.bin','inspection':{'app_id':%s,'platform':t['platform'],
'flavor':t['flavor'],'version':t['version'],'evidence':'fixture','native_guards':{'fixture-only':True}}}))
''' % ("'com.example.wrong'" if wrong else "t['app_id']"))
        return {'argv': [sys.executable, '{root}/helpers/build_fixture.py'], 'inputs': ['helpers'], 'artifact': 'app.bin'}

    def test_build_record_binds_actual_artifact_and_native_identity(self):
        target = self.profile['targets']['production']
        path = self.builds.build(self.root, target, self.adapter(), self.root / 'build-history', mode='fixture')
        record = module(self, 'snapshots').validate_snapshot(path)['record']
        self.assertEqual(record['version'], target['version'])
        self.assertEqual(record['app_id'], target['app_id'])
        self.assertEqual(record['evidence'], 'fixture')
        self.assertEqual((path / 'app.bin').read_bytes(), b'new fixture build')
        self.assertIn('helpers/build_fixture.py', record['source_inputs'])

    def test_wrong_native_identity_blocks_build_publication(self):
        with self.assertRaisesRegex(ValueError, 'identity|app_id'):
            self.builds.build(self.root, self.profile['targets']['production'], self.adapter(wrong=True),
                              self.root / 'build-history', mode='fixture')
        self.assertFalse((self.root / 'build-history').exists())

    def test_false_native_guard_blocks_live_publication(self):
        from unittest.mock import patch
        target = self.profile['targets']['production']
        adapter = self.adapter()
        adapter['inspect_argv'] = adapter['argv']
        original = self.builds.run_command
        def inspected(*args, **kwargs):
            result = original(*args, **kwargs)
            if args[1]['action'] == 'inspect':
                return dict(result['inspection'], evidence='inspected', native_guards={'production-entitlements': False})
            return result
        with patch.object(self.builds, 'git', return_value='a' * 40), patch.object(self.builds, 'run_command', side_effect=inspected):
            with self.assertRaisesRegex(ValueError, 'guard'):
                self.builds.build(self.root, target, adapter, self.root / 'build-history', mode='live', allow_build=True)

    def test_live_build_needs_explicit_authority_before_adapter(self):
        from unittest.mock import patch
        adapter = self.adapter()
        adapter['inspect_argv'] = adapter['argv']
        with patch.object(self.builds, 'run_command', side_effect=AssertionError('adapter called')):
            with self.assertRaisesRegex(ValueError, 'authority|allow_build'):
                self.builds.build(self.root, self.profile['targets']['production'], adapter,
                                  self.root / 'build-history', mode='live')

    def test_inspector_cannot_change_the_artifact_it_just_verified(self):
        from pathlib import Path
        from unittest.mock import patch
        adapter = self.adapter()
        adapter['inspect_argv'] = adapter['argv']
        original = self.builds.run_command
        def mutate(*args, **kwargs):
            if args[1]['action'] != 'inspect':
                return original(*args, **kwargs)
            request = args[1]
            Path(request['artifact']).write_bytes(b'replaced after inspection')
            return dict(request['target'], evidence='fixture', native_guards={'fixture-only': True})
        with patch.object(self.builds, 'run_command', side_effect=mutate):
            with self.assertRaisesRegex(ValueError, 'changed during native inspection'):
                self.builds.build(self.root, self.profile['targets']['production'], adapter,
                                  self.root / 'build-history', mode='fixture')
        self.assertFalse((self.root / 'build-history').exists())


if __name__ == '__main__':
    unittest.main()
