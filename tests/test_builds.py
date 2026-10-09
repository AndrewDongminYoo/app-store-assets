import sys
import json
import shutil
import unittest
from pathlib import Path
from unittest.mock import patch

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

    def test_build_and_inspect_execute_captured_entrypoint_and_helpers(self):
        marker = self.root / 'selected-build-code.json'
        script = self.root / 'helpers/build_fixture.py'
        helper = self.root / 'helpers/bound_helper.py'
        source = '''import json,sys,pathlib,bound_helper
r=json.load(sys.stdin);t=r['target']
pathlib.Path(%s+'.'+r['action']).write_text(json.dumps({'action':r['action'],'code':bound_helper.CODE,'signing':r['signing_file']}))
if r['action']=='build':
 pathlib.Path(r['output'],'app.bin').write_bytes(b'approved fixture build')
 print(json.dumps({'artifact':'app.bin'}))
else: print(json.dumps(dict(t,evidence='fixture',native_guards={'fixture-only':True})))
''' % repr(str(marker))
        script.write_text(source)
        helper.write_text('CODE="approved"\n')
        argv = [sys.executable,'{root}/helpers/build_fixture.py']
        adapter = {'argv':argv,'inspect_argv':argv,'inputs':['helpers'],'artifact':'app.bin'}
        original = self.builds.run_command
        for action in ['build','inspect']:
            for change in ['entry','helper','parent']:
                with self.subTest(action=action, change=change):
                    def replace(argv, request, cwd, home, action=action, change=change, **kwargs):
                        if request['action'] != action:
                            return original(argv,request,cwd,home,**kwargs)
                        cwd = Path(cwd)
                        old_parent = cwd.with_name('saved-inputs')
                        if change=='parent':
                            cwd.rename(old_parent)
                            shutil.copytree(old_parent,cwd)
                        changed = cwd/'helpers'/('build_fixture.py' if change=='entry' else 'bound_helper.py')
                        before = changed.read_bytes()
                        replacement = changed.with_name('replacement-source')
                        replacement.write_text(source.replace('bound_helper.CODE',repr('unreviewed')) if change=='entry' else 'CODE="unreviewed"\n')
                        replacement.replace(changed)
                        try:
                            return original(argv,request,cwd,home,**kwargs)
                        finally:
                            if change=='parent':
                                shutil.rmtree(cwd)
                                old_parent.rename(cwd)
                            else:
                                changed.unlink()
                                changed.write_bytes(before)
                                changed.chmod(0o444)
                    with patch.object(self.builds,'run_command',side_effect=replace):
                        self.builds.build(self.root,self.profile['targets']['production'],adapter,self.root/'history',mode='fixture',signing_file='/nonexistent-public-fixture-signing')
                    observed = json.loads(marker.with_name(marker.name+'.'+action).read_text())
                    self.assertEqual(observed['code'],'approved')

    def test_unbound_build_module_loader_stops_before_launch(self):
        marker = self.root/'unbound-build-ran'
        adapter = self.adapter()
        script = self.root/'helpers/build_fixture.py'
        script.write_text(script.read_text().replace('r=json.load(sys.stdin)',"pathlib.Path(%s).write_text('unreviewed');r=json.load(sys.stdin)" % repr(str(marker))))
        adapter['argv'] = [sys.executable,'-m','helpers.build_fixture']
        with self.assertRaisesRegex(ValueError,'entrypoint|unbound'):
            self.builds.build(self.root,self.profile['targets']['production'],adapter,self.root/'history',mode='fixture')
        self.assertFalse(marker.exists())

    def test_published_build_cannot_differ_from_inspected_digest(self):
        publish = self.builds.publish_snapshot
        def replace(root, record, files, **kwargs):
            next(iter(files.values())).write_bytes(b'replaced after recorded inspection')
            return publish(root,record,files,**kwargs)
        with patch.object(self.builds,'publish_snapshot',side_effect=replace):
            with self.assertRaisesRegex(ValueError,'inspected|artifact|digest|hash'):
                self.builds.build(self.root,self.profile['targets']['production'],self.adapter(),self.root/'history',mode='fixture')
        self.assertFalse(list((self.root/'history').glob('[0-9a-f]'*64)))

    def test_captured_build_can_copy_reviewed_sources_to_its_output_workspace(self):
        script = self.root/'helpers/copy_build.py'
        (self.root/'helpers/input.bin').write_bytes(b'approved copied artifact')
        script.write_text('''import json,pathlib,shutil,sys
r=json.load(sys.stdin);t=r['target'];output=pathlib.Path(r['output'])
shutil.copytree('helpers',output/'workspace')
shutil.copyfile('helpers/input.bin',output/'app.bin')
print(json.dumps({'artifact':'app.bin','inspection':dict(t,evidence='fixture',native_guards={'fixture-only':True})}))
''')
        adapter = {'argv':[sys.executable,'{root}/helpers/copy_build.py'],'inputs':['helpers'],'artifact':'app.bin'}
        path = self.builds.build(self.root,self.profile['targets']['production'],adapter,self.root/'history',mode='fixture')
        self.assertEqual((path/'app.bin').read_bytes(),b'approved copied artifact')

    def test_build_captures_close_on_success_and_prelaunch_failure(self):
        capture = self.builds.capture_provider_argv
        for case in ['success','wrong-identity','unbound-inspector']:
            with self.subTest(case=case):
                captured = []
                def retain(*args, captured=captured, **kwargs):
                    result = capture(*args, **kwargs)
                    captured.append(result)
                    return result
                adapter = self.adapter(wrong=case=='wrong-identity')
                if case=='unbound-inspector':
                    adapter['inspect_argv'] = [sys.executable,'-m','unbound.inspector']
                with patch.object(self.builds,'capture_provider_argv',side_effect=retain):
                    if case=='success':
                        self.builds.build(self.root,self.profile['targets']['production'],adapter,self.root/'history',mode='fixture')
                    else:
                        with self.assertRaises(ValueError):
                            self.builds.build(self.root,self.profile['targets']['production'],adapter,self.root/'history',mode='fixture')
                self.assertTrue(captured)
                self.assertTrue(all(argv.capture.closed for argv in captured))


if __name__ == '__main__':
    unittest.main()
