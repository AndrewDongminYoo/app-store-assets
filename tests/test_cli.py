import json
import os
import subprocess
import sys
import unittest
from unittest.mock import patch
from contextlib import redirect_stdout, redirect_stderr
import io

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

    def test_local_roundtrip_and_regeneration_dry_runs_read_no_source_and_write_nothing(self):
        (self.root / 'helpers/provider.py').write_text('raise RuntimeError("adapter must not run")\n')
        before = {p.relative_to(self.root).as_posix(): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        for command in ('export', 'import', 'regenerate'):
            with self.subTest(command=command):
                result = self.cli(command, '--source', 'missing-input', '--output', 'new-output', '--dry-run')
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(json.loads(result.stdout)['status'], 'dry-run')
        after = {p.relative_to(self.root).as_posix(): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        self.assertEqual(before, after)

    def test_build_dry_run_displays_adapter_without_reading_signing_or_launching_it(self):
        argv = [sys.executable, '{root}/helpers/missing_build_adapter.py']
        self.profile['targets']['production']['build'] = 'production'
        self.profile['builds'] = {'production': {'argv': argv, 'inspect_argv': argv,
                                               'inputs': ['missing-source'], 'artifact': 'app.bin'}}
        write_json(self.root / 'store-upload.json', self.profile)
        result = self.cli('build', '--dry-run', '--allow-build', '--signing-file', '/missing-protected/signing.json')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['adapter_argv'], argv)
        self.assertFalse((self.root / 'build/store-assets').exists())

    def test_existing_receipt_blocks_before_constructing_provider(self):
        from app_store_assets import cli
        plan = json.loads(self.cli('plan').stdout)
        write_json(self.root / 'approved.json', plan)
        write_json(self.root / 'existing.json', {'preserve': True})
        with patch.object(cli, 'CommandProvider', side_effect=AssertionError('provider constructed')), redirect_stderr(io.StringIO()):
            result = cli.main(['execute', '--root', str(self.root), '--target', 'production',
                               '--plan', 'approved.json', '--expected-digest', plan['digest'],
                               '--receipt', 'existing.json', '--allow-effects'])
        self.assertEqual(result, 1)

    def test_verify_dry_run_has_no_provider_or_receipt_write(self):
        from app_store_assets import cli
        from app_store_assets.execution import execute
        from test_execution import FakeProvider
        plan = json.loads(self.cli('plan').stdout)
        receipt = execute(self.root, plan, plan['digest'], FakeProvider(self.root), self.root / 'build/store-assets')
        path = self.root / 'build/store-assets/attempts' / receipt['attempt'] / 'receipt.json'
        original = path.read_bytes()
        with patch.object(cli, 'CommandProvider', side_effect=AssertionError('dry run provider')), redirect_stdout(io.StringIO()):
            result = cli.main(['verify', '--root', str(self.root), '--target', 'production',
                               '--receipt', path.relative_to(self.root).as_posix(), '--dry-run'])
        self.assertEqual(result, 0)
        self.assertEqual(path.read_bytes(), original)


if __name__ == '__main__':
    unittest.main()
