import os
import shutil
import subprocess
import sys
import unittest

from pipeline_support import ROOT, fixture


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        self.root, self.profile = fixture(self)
        self.script = self.root / 'scripts/store_assets/bootstrap.py'
        self.script.parent.mkdir(parents=True)
        template = ROOT / 'examples/consumer_bootstrap.py'
        self.assertTrue(template.is_file(), 'missing verified consumer bootstrap')
        shutil.copyfile(template, self.script)

    def run_bootstrap(self, *args, env=None):
        return subprocess.run([sys.executable, '-I', '-S', str(self.script), 'doctor', '--target', 'production', *args],
                              env=env or dict(os.environ, PYTHONDONTWRITEBYTECODE='1'), capture_output=True, text=True)

    def test_verified_runtime_is_imported_without_home_state(self):
        result = self.run_bootstrap(env={'PATH': os.environ['PATH'], 'HOME': str(self.root / 'empty-home')})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(self.profile['runtime']['commit'], result.stdout)

    def test_changed_runtime_is_rejected_before_import(self):
        runtime = self.root / self.profile['runtime']['path']
        (runtime / 'assets.py').write_text('raise AssertionError("unverified code executed")')
        result = self.run_bootstrap()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('runtime', result.stderr)
        self.assertNotIn('AssertionError', result.stderr)

    def test_mutation_after_verification_cannot_execute_modified_runtime(self):
        wrapper = '''import importlib.util,pathlib,sys
s=importlib.util.spec_from_file_location('bootstrap',sys.argv[1]);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
verify=m.verify
def changed():
 result=verify();runtime=result[0] if isinstance(result,tuple) else result
 (runtime/'assets.py').write_text('raise AssertionError("unverified runtime executed")')
 return result
m.verify=changed;sys.argv=[sys.argv[1],'doctor','--target','production'];sys.exit(m.main())
'''
        result = subprocess.run([sys.executable, '-I', '-S', '-c', wrapper, str(self.script)], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('AssertionError', result.stderr)
        self.assertIn('runtime', result.stderr)

    def test_override_paths_and_home_runtime_are_rejected(self):
        for args, env in [(('--root', '/tmp'), None), (('--profile=foreign.json',), None),
                          ((), dict(os.environ, APP_STORE_ASSETS_ROOT='/tmp/unapproved'))]:
            with self.subTest(args=args, env=bool(env)):
                result = self.run_bootstrap(*args, env=env)
                self.assertNotEqual(result.returncode, 0)


if __name__ == '__main__':
    unittest.main()
