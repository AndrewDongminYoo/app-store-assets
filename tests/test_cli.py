import json
import os
import subprocess
import sys
import unittest

from pipeline_support import ROOT, fixture, write_json


class CliTests(unittest.TestCase):
    def setUp(self):
        self.root, self.profile = fixture(self)

    def cli(self, *args):
        return subprocess.run([sys.executable, str(ROOT / 'assets.py'), *args, '--root', str(self.root),
                               '--profile', 'store-upload.json', '--target', 'production'],
                              env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'), capture_output=True, text=True, timeout=30)

    def test_doctor_is_offline_and_reports_pinned_runtime(self):
        result = self.cli('doctor')
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report['runtime']['commit'], self.profile['runtime']['commit'])
        self.assertFalse(report['effects'])

    def test_plan_and_dry_run_do_not_run_adapter(self):
        (self.root / 'helpers/provider.py').write_text('raise RuntimeError("adapter must not run")\n')
        planned = self.cli('plan', '--operation', 'binary')
        self.assertEqual(planned.returncode, 0, planned.stderr)
        plan = json.loads(planned.stdout)
        write_json(self.root / 'approved.json', plan)
        result = self.cli('execute', '--plan', 'approved.json', '--expected-digest', plan['digest'], '--dry-run')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['status'], 'dry-run')
        self.assertFalse((self.root / 'build/store-assets').exists())

    def test_execute_without_effect_authority_cannot_launch_provider(self):
        planned = self.cli('plan', '--operation', 'binary')
        self.assertEqual(planned.returncode, 0, planned.stderr)
        plan = json.loads(planned.stdout)
        write_json(self.root / 'approved.json', plan)
        result = self.cli('execute', '--plan', 'approved.json', '--expected-digest', plan['digest'])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('effects', result.stderr)


if __name__ == '__main__':
    unittest.main()
