import json
import os
import shutil
import sys
import threading
import time
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

    def test_module_loader_without_captured_entrypoint_is_rejected_offline(self):
        files = {str(self.root / 'helpers/provider.py'): module(self, 'records').file_digest(self.root / 'helpers/provider.py')}
        for argv in ([sys.executable, '-m', 'unbound_adapter'], ['ruby', '-e', 'puts 1']):
            with self.subTest(argv=argv), self.assertRaisesRegex(ValueError, 'staged|entrypoint|loader'):
                self.commands.capture_provider_argv(argv, files)

    def test_python_helper_replacement_uses_captured_code(self):
        script = self.root / 'helpers/provider.py'
        script.write_text('import bound_helper,json; print(json.dumps({"code":bound_helper.CODE}))\n')
        helper = script.with_name('bound_helper.py')
        helper.write_text('CODE="approved"\n')
        provider = module(self, 'providers').CommandProvider(self.profile['targets']['production'], 'fixture', allow_effects=True)
        provider.bind_stage(self.root, self.root / 'tools/app-store-assets')
        helper.unlink()
        helper.write_text('CODE="unreviewed"\n')
        self.assertEqual(provider.request('snapshot'), {'code': 'approved'})

    def test_python_package_replacement_uses_captured_relative_imports(self):
        script = self.root / 'helpers/provider.py'
        script.write_text('from package import helper; import json; print(json.dumps({"code":helper.CODE}))\n')
        package = script.parent / 'package'
        package.mkdir()
        (package / '__init__.py').write_text('from . import helper\n')
        (package / 'helper.py').write_text('CODE="approved"\n')
        provider = module(self, 'providers').CommandProvider(self.profile['targets']['production'], 'fixture', allow_effects=True)
        provider.bind_stage(self.root, self.root / 'tools/app-store-assets')
        package.rename(package.with_name('old-package'))
        package.mkdir()
        (package / '__init__.py').write_text('from . import helper\n')
        (package / 'helper.py').write_text('CODE="unreviewed"\n')
        self.assertEqual(provider.request('snapshot'), {'code': 'approved'})

    def test_added_python_module_cannot_execute_outside_capture(self):
        script = self.root / 'helpers/provider.py'
        script.write_text('import added_module; import json; print(json.dumps({"code":added_module.CODE}))\n')
        provider = module(self, 'providers').CommandProvider(self.profile['targets']['production'], 'fixture', allow_effects=True)
        provider.bind_stage(self.root, self.root / 'tools/app-store-assets')
        marker = self.root / 'unexpected-effect'
        script.with_name('added_module.py').write_text('from pathlib import Path; Path('+repr(str(marker))+').touch(); CODE="unreviewed"\n')
        with self.assertRaises(ValueError):
            provider.request('snapshot')
        self.assertFalse(marker.exists())

    def test_python_dynamic_helper_reads_captured_bytes(self):
        script = self.root / 'helpers/provider.py'
        script.write_text('from pathlib import Path; import json; ns={}; exec(Path(__file__).with_name("helper.source").read_text(),ns); print(json.dumps({"code":ns["CODE"]}))\n')
        helper = script.with_name('helper.source')
        helper.write_text('CODE="approved"\n')
        provider = module(self, 'providers').CommandProvider(self.profile['targets']['production'], 'fixture', allow_effects=True)
        provider.bind_stage(self.root, self.root / 'tools/app-store-assets')
        helper.write_text('CODE="unreviewed"\n')
        self.assertEqual(provider.request('snapshot'), {'code': 'approved'})

    def test_ruby_dynamic_helper_reads_captured_bytes(self):
        script = self.root / 'helpers/provider.rb'
        script.write_text('eval(File.read(File.join(__dir__, "helper.source")),TOPLEVEL_BINDING); require "json"; puts JSON.generate({code:CODE})\n')
        helper = script.with_name('helper.source')
        helper.write_text('CODE="approved"\n')
        target = self.profile['targets']['production']
        target['provider']['argv'] = ['ruby', '{root}/helpers/provider.rb']
        provider = module(self, 'providers').CommandProvider(target, 'fixture', allow_effects=True)
        provider.bind_stage(self.root, self.root / 'tools/app-store-assets')
        helper.write_text('CODE="unreviewed"\n')
        self.assertEqual(provider.request('snapshot'), {'code': 'approved'})

    def test_python_explicit_source_loader_uses_captured_bytes(self):
        script = self.root / 'helpers/provider.py'
        script.write_text('import importlib.util,json; from pathlib import Path; spec=importlib.util.spec_from_file_location("loaded",Path(__file__).with_name("loaded.py")); helper=importlib.util.module_from_spec(spec); spec.loader.exec_module(helper); print(json.dumps({"code":helper.CODE}))\n')
        helper = script.with_name('loaded.py')
        helper.write_text('CODE="approved"\n')
        provider = module(self, 'providers').CommandProvider(self.profile['targets']['production'], 'fixture', allow_effects=True)
        provider.bind_stage(self.root, self.root / 'tools/app-store-assets')
        helper.write_text('CODE="unreviewed"\n')
        self.assertEqual(provider.request('snapshot'), {'code': 'approved'})

    def test_ruby_added_helper_is_blocked_without_executing_it(self):
        script = self.root / 'helpers/provider.rb'
        script.write_text('require_relative "added_helper"; require "json"; puts JSON.generate({code:CODE})\n')
        target = self.profile['targets']['production']
        target['provider']['argv'] = ['ruby', '{root}/helpers/provider.rb']
        provider = module(self, 'providers').CommandProvider(target, 'fixture', allow_effects=True)
        provider.bind_stage(self.root, self.root / 'tools/app-store-assets')
        marker = self.root / 'unexpected-ruby-effect'
        script.with_name('added_helper.rb').write_text('File.write('+json.dumps(str(marker))+', "unreviewed"); CODE="unreviewed"\n')
        with self.assertRaises(ValueError):
            provider.request('snapshot')
        self.assertFalse(marker.exists())

    def test_running_python_provider_keeps_capture_after_working_directory_rename(self):
        ready = self.root.with_name(self.root.name + '-ready')
        release = self.root.with_name(self.root.name + '-release')
        self.addCleanup(lambda: ready.unlink(missing_ok=True))
        self.addCleanup(lambda: release.unlink(missing_ok=True))
        script = self.root / 'helpers/provider.py'
        script.write_text('from pathlib import Path; import json,time\n'
                          'Path('+repr(str(ready))+').touch()\n'
                          'deadline=time.monotonic()+10\n'
                          'while not Path('+repr(str(release))+').exists():\n'
                          ' if time.monotonic()>deadline: raise RuntimeError("test synchronization timed out")\n'
                          ' time.sleep(0.01)\n'
                          'ns={};exec((Path.cwd()/"helpers/helper.source").read_text(),ns);print(json.dumps({"code":ns["CODE"]}))\n')
        helper = script.with_name('helper.source')
        helper.write_text('CODE="approved"\n')
        provider = module(self, 'providers').CommandProvider(self.profile['targets']['production'], 'fixture', allow_effects=True)
        provider.bind_stage(self.root, self.root / 'tools/app-store-assets')
        results, errors = [], []
        def request():
            try:
                results.append(provider.request('snapshot'))
            except Exception as error:
                errors.append(error)
        worker = threading.Thread(target=request)
        worker.start()
        deadline = time.monotonic() + 10
        while not ready.exists() and worker.is_alive() and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertTrue(ready.exists(), errors)
        displaced = self.root.with_name(self.root.name + '-displaced')
        self.root.rename(displaced)
        self.addCleanup(shutil.rmtree, displaced)
        self.root.mkdir()
        (displaced / 'helpers/helper.source').write_text('CODE="unreviewed"\n')
        release.touch()
        worker.join(15)
        self.assertFalse(worker.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(results, [{'code': 'approved'}])

    def test_ruby_file_constructor_uses_captured_helper_bytes(self):
        script = self.root / 'helpers/provider.rb'
        script.write_text('eval(File.new(File.join(__dir__, "helper.source"),"r").read,TOPLEVEL_BINDING); require "json"; puts JSON.generate({code:CODE})\n')
        helper = script.with_name('helper.source')
        helper.write_text('CODE="approved"\n')
        target = self.profile['targets']['production']
        target['provider']['argv'] = ['ruby', '{root}/helpers/provider.rb']
        provider = module(self, 'providers').CommandProvider(target, 'fixture', allow_effects=True)
        provider.bind_stage(self.root, self.root / 'tools/app-store-assets')
        helper.write_text('CODE="unreviewed"\n')
        self.assertEqual(provider.request('snapshot'), {'code': 'approved'})

    def test_ruby_raw_staged_open_cannot_execute_uncaptured_helper(self):
        script = self.root / 'helpers/provider.rb'
        script.write_text('fd=File.sysopen(File.join(__dir__, "helper.source")); eval(IO.new(fd).read,TOPLEVEL_BINDING); require "json"; puts JSON.generate({code:CODE})\n')
        helper = script.with_name('helper.source')
        helper.write_text('CODE="approved"\n')
        target = self.profile['targets']['production']
        target['provider']['argv'] = ['ruby', '{root}/helpers/provider.rb']
        provider = module(self, 'providers').CommandProvider(target, 'fixture', allow_effects=True)
        provider.bind_stage(self.root, self.root / 'tools/app-store-assets')
        marker = self.root / 'unexpected-raw-effect'
        helper.write_text('File.write('+json.dumps(str(marker))+', "unreviewed"); CODE="unreviewed"\n')
        with self.assertRaises(ValueError):
            provider.request('snapshot')
        self.assertFalse(marker.exists())

    def test_ruby_helper_replacement_uses_captured_require_relative_and_load(self):
        script = self.root / 'helpers/provider.rb'
        script.write_text('require_relative "bound_helper"; load File.join(__dir__, "loaded.rb"); require "json"; puts JSON.generate({code:CODE, loaded:LOADED})\n')
        helper = script.with_name('bound_helper.rb')
        loaded = script.with_name('loaded.rb')
        helper.write_text('CODE="approved"\n')
        loaded.write_text('LOADED="approved"\n')
        target = self.profile['targets']['production']
        target['provider']['argv'] = ['ruby', '{root}/helpers/provider.rb']
        provider = module(self, 'providers').CommandProvider(target, 'fixture', allow_effects=True)
        provider.bind_stage(self.root, self.root / 'tools/app-store-assets')
        helper.write_text('CODE="unreviewed"\n')
        loaded.write_text('LOADED="unreviewed"\n')
        self.assertEqual(provider.request('snapshot'), {'code': 'approved', 'loaded': 'approved'})

    def test_ruby_gemfile_parent_replacement_uses_captured_gemfile_and_lock(self):
        ruby = shutil.which('ruby')
        script = self.root / 'helpers/provider.rb'
        marker = self.root / 'unexpected-gemfile-effect'
        script.write_text('require "json"; puts JSON.generate({code:"approved"})\n')
        (self.root / 'Gemfile').write_text('# no dependencies or network resolution\n')
        (self.root / 'Gemfile.lock').write_text('GEM\n  specs:\n\nPLATFORMS\n  ruby\n\nDEPENDENCIES\n')
        target = self.profile['targets']['production']
        target['provider'].update(argv=[ruby, '-r', 'bundler/setup', '{root}/helpers/provider.rb'], gemfile='Gemfile')
        provider = module(self, 'providers').CommandProvider(target, 'fixture', allow_effects=True)
        provider.bind_stage(self.root, self.root / 'tools/app-store-assets')
        displaced = self.root.with_name(self.root.name + '-displaced')
        self.root.rename(displaced)
        self.addCleanup(shutil.rmtree, displaced)
        self.root.mkdir()
        (self.root / 'Gemfile').write_text('File.write('+json.dumps(str(marker))+', "unreviewed"); raise "replacement Gemfile"\n')
        (self.root / 'Gemfile.lock').write_text('unreviewed lockfile\n')
        result = None
        try:
            result = provider.request('snapshot')
        except ValueError:
            pass
        self.assertFalse(marker.exists())
        self.assertEqual(result, {'code': 'approved'})

    def test_ruby_relative_load_uses_capture_for_working_directory_and_load_path(self):
        script = self.root / 'helpers/provider.rb'
        helper = self.root / 'loaded.rb'
        nested = self.root / 'helpers/loaded.rb'
        target = self.profile['targets']['production']
        target['provider']['argv'] = ['ruby', '{root}/helpers/provider.rb']
        cases = [('', 'loaded.rb'), ('', 'helpers/loaded.rb'), ('', './helpers/loaded.rb'),
                 ('$LOAD_PATH.unshift(__dir__); ', 'loaded.rb')]
        for setup, name in cases:
            with self.subTest(loader=name, setup=setup):
                script.write_text(setup+'load '+json.dumps(name)+'; require "json"; puts JSON.generate({code:CODE})\n')
                helper.write_text('CODE="approved"\n')
                nested.write_text('CODE="approved"\n')
                provider = module(self, 'providers').CommandProvider(target, 'fixture', allow_effects=True)
                provider.bind_stage(self.root, self.root / 'tools/app-store-assets')
                helper.write_text('CODE="unreviewed"\n')
                nested.write_text('CODE="unreviewed"\n')
                self.assertEqual(provider.request('snapshot'), {'code': 'approved'})

    def test_relative_ruby_load_rejects_added_working_directory_helper(self):
        script = self.root / 'helpers/provider.rb'
        script.write_text('load "added.rb"; require "json"; puts JSON.generate({code:CODE})\n')
        target = self.profile['targets']['production']
        target['provider']['argv'] = ['ruby', '{root}/helpers/provider.rb']
        provider = module(self, 'providers').CommandProvider(target, 'fixture', allow_effects=True)
        provider.bind_stage(self.root, self.root / 'tools/app-store-assets')
        marker = self.root / 'unexpected-relative-load'
        (self.root / 'added.rb').write_text('File.write('+json.dumps(str(marker))+', "unreviewed"); CODE="unreviewed"\n')
        with self.assertRaises(ValueError):
            provider.request('snapshot')
        self.assertFalse(marker.exists())

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
