import copy
import json
import os
import shutil
import subprocess
import sys
import unittest
from unittest.mock import patch
from contextlib import redirect_stdout, redirect_stderr
import io

from pipeline_support import ROOT, fixture, git, write_json


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

    def test_execute_uses_reviewed_adapter_when_initial_profile_is_restored(self):
        from app_store_assets import cli
        source = """import json,pathlib,sys
request=json.load(sys.stdin)
root=pathlib.Path(request['root'])
if request['action']=='snapshot':
 print((root/'remote.json').read_text())
elif request['action']=='upload':
 (root.parent/'selected-provider.txt').write_text('approved')
 print(json.dumps({'accepted':True}))
else:
 payload=request['plan']['payload'];target=payload['target']
 print(json.dumps({'target':target,'observed':{'binary':{'app_id':target['app_id'],'version':target['version'],'platform':target['platform'],'source_sha256':payload['build']['sha256'],'processing_state':'processed'},'release_status':payload['release_status'],'release_notes':payload['release_notes']}}))
"""
        (self.root / 'helpers/provider.py').write_text(source)
        (self.root / 'helpers/other.py').write_text(source.replace("write_text('approved')", "write_text('unreviewed')"))
        planned = self.cli('plan', '--operation', 'binary')
        self.assertEqual(planned.returncode, 0, planned.stderr)
        plan = json.loads(planned.stdout)
        write_json(self.root / 'approved.json', plan)
        profile_path = self.root / 'store-upload.json'
        approved = profile_path.read_bytes()
        stale = copy.deepcopy(self.profile)
        stale['targets']['production']['provider']['argv'] = [sys.executable, '{root}/helpers/other.py']
        write_json(profile_path, stale)
        real_load = cli.load_profile
        def restore_after_load(*args):
            result = real_load(*args)
            profile_path.write_bytes(approved)
            return result
        with patch.object(cli, 'load_profile', side_effect=restore_after_load), redirect_stdout(io.StringIO()):
            result = cli.main(['execute','--root',str(self.root),'--target','production','--plan','approved.json',
                               '--expected-digest',plan['digest'],'--allow-effects'])
        self.assertEqual(result, 0)
        selected = next((self.root / 'build/store-assets/attempts').glob('*/selected-provider.txt'))
        self.assertEqual(selected.read_text(), 'approved')

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

    def test_unaccepted_partial_receipt_cannot_verify_an_existing_binary(self):
        from app_store_assets import cli, execution, planning
        from test_execution import FakeProvider
        for store in ['apple', 'google']:
            root, _ = fixture(self, store=store)
            plan = planning.make_plan(root, 'store-upload.json', 'production', 'binary')
            provider = FakeProvider(root)
            provider.bind_stage = lambda *args: None
            def reject(_):
                raise ValueError('native duplicate rejected without transfer')
            provider.on_upload = reject
            with self.assertRaises(ValueError):
                execution.execute(root, plan, plan['digest'], provider, root/'build/store-assets')
            path = next((root/'build/store-assets/attempts').glob('*/receipt.json'))
            original = path.read_bytes()
            real_readback = provider.readback
            def existing(*args, real_readback=real_readback):
                report = real_readback(*args)
                report['observed']['binary']['source_sha256'] = None
                return report
            provider.readback = existing
            stderr = io.StringIO()
            with patch.object(cli.CommandProvider, 'from_plan', return_value=provider) as factory, redirect_stdout(io.StringIO()), redirect_stderr(stderr):
                result = cli.main(['verify','--root',str(root),'--target','production','--receipt',str(path.relative_to(root)),'--allow-effects'])
            with self.subTest(store=store):
                self.assertEqual(result, 1)
                self.assertIn('acceptance', stderr.getvalue())
                factory.assert_not_called()
                self.assertEqual(path.read_bytes(), original)
                self.assertEqual(provider.writes, [])

    def test_accepted_pending_receipt_can_be_verified(self):
        from app_store_assets import cli, execution, planning
        from test_execution import FakeProvider
        plan = planning.make_plan(self.root, 'store-upload.json', 'production', 'binary')
        provider = FakeProvider(self.root)
        provider.bind_stage = lambda *args: None
        provider.pending = True
        receipt = execution.execute(self.root, plan, plan['digest'], provider, self.root/'build/store-assets')
        self.assertEqual(receipt['status'], 'accepted_pending_verification')
        provider.pending = False
        path = self.root/'build/store-assets/attempts'/receipt['attempt']/'receipt.json'
        with patch.object(cli.CommandProvider, 'from_plan', return_value=provider), redirect_stdout(io.StringIO()):
            result = cli.main(['verify','--root',str(self.root),'--target','production','--receipt',str(path.relative_to(self.root)),'--allow-effects'])
        self.assertEqual(result, 0)
        self.assertEqual(json.loads(path.read_text())['status'], 'verified')

    def test_accepted_partial_receipt_can_be_reconciled_after_restoring_staged_inputs(self):
        from app_store_assets import cli, execution, planning
        from test_execution import FakeProvider
        plan = planning.make_plan(self.root, 'store-upload.json', 'production', 'binary')
        provider = FakeProvider(self.root)
        provider.bind_stage = lambda *args: None
        restored = {}
        def alter(_):
            helper = next((self.root/'build/store-assets/attempts').glob('*/inputs/helpers/version_guard.rb'))
            restored.update(path=helper, data=helper.read_bytes())
            helper.chmod(0o644)
            helper.write_text('fixture failure after actual fake acceptance')
        provider.on_upload = alter
        with self.assertRaises(ValueError):
            execution.execute(self.root, plan, plan['digest'], provider, self.root/'build/store-assets')
        path = next((self.root/'build/store-assets/attempts').glob('*/receipt.json'))
        receipt = json.loads(path.read_text())
        self.assertEqual(receipt['status'], 'failed_partial')
        self.assertIs(receipt.get('provider_result', {}).get('accepted'), True)
        restored['path'].write_bytes(restored['data'])
        restored['path'].chmod(0o444)
        with patch.object(cli.CommandProvider, 'from_plan', return_value=provider), redirect_stdout(io.StringIO()):
            result = cli.main(['verify','--root',str(self.root),'--target','production','--receipt',str(path.relative_to(self.root)),'--allow-effects'])
        self.assertEqual(result, 0)
        self.assertEqual(json.loads(path.read_text())['status'], 'verified')
        self.assertEqual(provider.writes[0]['bytes'], b'approved artifact')

    def test_changed_runtime_profile_blocks_execute_and_verify_before_provider(self):
        from app_store_assets import cli
        from app_store_assets.planning import make_plan
        from app_store_assets.identity import runtime_inventory
        second = self.root / 'tools/reviewed-runtime'
        shutil.copytree(self.root / 'tools/app-store-assets', second)
        executor = second / 'app_store_assets/execution.py'
        executor.write_text(executor.read_text() + '\n# different reviewed runtime\n')
        git(second, 'add', 'app_store_assets/execution.py')
        git(second, 'commit', '-qm', 'Synthetic alternate runtime')
        approved = copy.deepcopy(self.profile)
        approved['runtime'].update(path='tools/reviewed-runtime', commit=git(second, 'rev-parse', 'HEAD'),
                                   files=runtime_inventory(second))
        write_json(self.root / 'store-upload.json', approved)
        plan = make_plan(self.root, 'store-upload.json', 'production', 'binary')
        write_json(self.root / 'approved.json', plan)
        write_json(self.root / 'attempt/plan.json', plan)
        write_json(self.root / 'attempt/receipt.json', {'digest':plan['digest'],'target':plan['payload']['target']})
        real_load = cli.load_profile
        def restore(*args):
            result = real_load(*args)
            write_json(self.root / 'store-upload.json', approved)
            return result
        for command in ['execute','verify']:
            with self.subTest(command=command):
                write_json(self.root / 'store-upload.json', self.profile)
                stderr = io.StringIO()
                args = ['--plan','approved.json','--expected-digest',plan['digest']] if command=='execute' else ['--receipt','attempt/receipt.json']
                with patch.object(cli, 'load_profile', side_effect=restore), patch.object(cli.CommandProvider,'from_plan',side_effect=AssertionError('unreviewed runtime reached provider')), redirect_stderr(stderr):
                    result = cli.main([command,'--root',str(self.root),'--target','production','--allow-effects',*args])
                self.assertEqual(result, 1)
                self.assertIn('runtime', stderr.getvalue())
        self.assertFalse((self.root / 'build/store-assets').exists())


if __name__ == '__main__':
    unittest.main()
