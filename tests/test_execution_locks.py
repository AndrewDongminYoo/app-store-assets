"""Real process locks in temporary fixture workspaces; no provider network."""
import json
import os
import subprocess
import sys
import unittest

from pipeline_support import ROOT, fixture, module, write_json
from test_execution import FakeProvider


class ExecutionLockTests(unittest.TestCase):
    def setUp(self):
        self.root, self.profile = fixture(self)
        self.execution = module(self, 'execution')
        self.plan = module(self, 'planning').make_plan(self.root, 'store-upload.json', 'production', 'binary')
        self.provider = FakeProvider(self.root)
        write_json(self.root / 'approved.json', self.plan)

    def execute(self):
        return self.execution.execute(self.root, self.plan, self.plan['digest'], self.provider,
                                      self.root / 'build/store-assets')

    def hold_and_kill(self, after_effects):
        source = '''import json,sys,time
from pathlib import Path
sys.path.insert(0, sys.argv[1]); sys.path.insert(0, sys.argv[1]+'/tests')
from app_store_assets.execution import execute
from test_execution import FakeProvider
root=Path(sys.argv[2]); plan=json.loads((root/'approved.json').read_text())
provider=FakeProvider(root)
def held(_):
    print('held', flush=True)
    while True: time.sleep(0.05)
if sys.argv[3]=='effects': provider.on_upload=held
else: provider.on_snapshot=held
execute(root,plan,plan['digest'],provider,root/'build/store-assets')
'''
        child = subprocess.Popen([sys.executable, '-u', '-c', source, str(ROOT), str(self.root),
                                  'effects' if after_effects else 'preflight'], stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE, text=True,
                                 env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'))
        try:
            import selectors
            with selectors.DefaultSelector() as ready:
                ready.register(child.stdout, selectors.EVENT_READ)
                self.assertTrue(ready.select(20), 'fixture child did not reach the held lock')
                self.assertEqual(child.stdout.readline().strip(), 'held')
            with self.assertRaisesRegex(ValueError, 'lock|concurrent'):
                self.execute()
            self.assertEqual(self.provider.reads, [])
        finally:
            child.kill()
            child.communicate(timeout=10)

    def test_killed_preflight_releases_lock_and_allows_safe_new_attempt(self):
        self.hold_and_kill(after_effects=False)
        self.assertEqual(self.execute()['status'], 'verified')
        self.assertEqual(len(self.provider.writes), 1)

    def test_killed_transfer_releases_lock_but_pending_receipt_blocks_retry(self):
        self.hold_and_kill(after_effects=True)
        with self.assertRaisesRegex(ValueError, 'pending|partial|recovery'):
            self.execute()
        self.assertEqual(self.provider.reads, [])
        self.assertEqual(self.provider.writes, [])
        receipts = list((self.root / 'build/store-assets/attempts').glob('*/receipt.json'))
        self.assertEqual(len(receipts), 1)
        self.assertTrue(json.loads(receipts[0].read_text())['effects_started'])
