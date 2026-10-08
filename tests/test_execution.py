import copy
import hashlib
import json
import os
import unittest
from unittest.mock import patch

from pipeline_support import fixture, module, write_json
from test_assets import png


class FakeProvider:
    def __init__(self, root):
        self.root = root
        self.remote = json.loads((root / 'remote.json').read_text())
        self.reads = []
        self.writes = []
        self.on_snapshot = None
        self.on_upload = None
        self.pending = False

    def snapshot(self, target):
        self.reads.append(copy.deepcopy(target))
        if self.on_snapshot:
            self.on_snapshot(self)
        return copy.deepcopy(self.remote)

    def upload(self, plan, staged_root):
        payload = plan['payload']
        if self.on_upload:
            self.on_upload(self)
        data = (staged_root / payload['artifact']['path']).read_bytes() if payload['artifact'] else None
        self.writes.append({'bytes': data, 'payload': payload, 'stage': staged_root})
        return {'accepted': True, 'remote_ids': []}

    def readback(self, plan, result):
        if self.pending:
            return {'target': plan['payload']['target'], 'observed': {}}
        payload = plan['payload']
        if payload['operation'] != 'binary':
            return {'target': payload['target'], 'observed': {'fields': payload['listing']['fields'],
                                                            'images': payload['listing']['images']}}
        return {'target': payload['target'], 'observed': {
            'binary': {'app_id': payload['target']['app_id'], 'version': payload['target']['version'], 'platform': payload['target']['platform'],
                       'source_sha256': payload['build']['sha256'], 'processing_state': 'processed'},
            'release_status': payload['release_status'], 'release_notes': payload['release_notes']}}


class ExecutionTests(unittest.TestCase):
    def setUp(self):
        self.executor = module(self, 'execution')
        self.planning = module(self, 'planning')
        self.root, self.profile = fixture(self)
        self.provider = FakeProvider(self.root)

    def plan(self, operation='binary'):
        return self.planning.make_plan(self.root, 'store-upload.json', 'production', operation)

    def execute(self, plan=None, **kwargs):
        plan = plan or self.plan()
        return self.executor.execute(self.root, plan, plan['digest'], self.provider, self.root / 'build/store-assets', **kwargs)

    def test_artifact_replaced_during_remote_lookup_uploads_reviewed_staged_bytes(self):
        self.provider.on_snapshot = lambda _: (self.root / 'artifacts/app.bin').write_bytes(b'replaced during lookup')
        receipt = self.execute()
        self.assertEqual(self.provider.writes[0]['bytes'], b'approved artifact')
        self.assertNotEqual(self.provider.writes[0]['stage'], self.root)
        self.assertEqual(receipt['status'], 'verified')

    def test_two_editable_versions_do_not_allow_highest_version_fallback(self):
        plan = self.plan('metadata')
        self.provider.remote['version_id'] = 'editable-1.1'
        self.provider.remote['target']['version']['name'] = '1.1'
        with self.assertRaisesRegex(ValueError, 'target|snapshot|version'):
            self.execute(plan)
        self.assertEqual(self.provider.writes, [])
        self.assertEqual(self.provider.reads[0]['version'], {'name': '1.0', 'build': '9'})

    def test_apple_metadata_write_binds_exact_existing_version_id(self):
        plan = self.plan('metadata')
        receipt = self.execute(plan)
        payload = self.provider.writes[0]['payload']
        self.assertEqual(payload['remote']['version_id'], 'editable-1.0')
        self.assertEqual(payload['target']['version']['name'], '1.0')
        self.assertEqual(receipt['status'], 'verified')

    def test_remote_only_ipad_class_blocks_partial_replacement(self):
        listing = json.loads((self.root / 'metadata/listing.json').read_text())
        (self.root / 'images').mkdir()
        (self.root / 'images/01.png').write_bytes(png())
        listing['images'] = {'en-US': {'APP_IPHONE_65': [{'file': 'images/01.png', 'sha256': hashlib.sha256(png()).hexdigest()}]}}
        write_json(self.root / 'metadata/listing.json', listing)
        remote = json.loads((self.root / 'remote.json').read_text())
        remote['images'] = {'en-US': {'APP_IPAD_PRO_129': [{'id': 'remote-ipad'}]}}
        write_json(self.root / 'remote.json', remote)
        self.provider.remote = remote
        self.profile['targets']['production']['replacement'] = {
            'locales': ['en-US'], 'slots': ['APP_IPHONE_65'], 'allow_delete': False}
        write_json(self.root / 'store-upload.json', self.profile)
        with self.assertRaisesRegex(ValueError, 'omitted|class|inventory'):
            self.execute(self.plan('images'))
        self.assertEqual(self.provider.writes, [])

    def test_existing_screenshot_deletion_requires_explicit_policy(self):
        (self.root / 'images').mkdir()
        data = png()
        (self.root / 'images/01.png').write_bytes(data)
        listing = json.loads((self.root / 'metadata/listing.json').read_text())
        listing['images'] = {'en-US': {'APP_IPHONE_65': [{'file': 'images/01.png', 'sha256': hashlib.sha256(data).hexdigest()}]}}
        write_json(self.root / 'metadata/listing.json', listing)
        self.provider.remote['images'] = {'en-US': {'APP_IPHONE_65': [{'id': 'existing'}]}}
        write_json(self.root / 'remote.json', self.provider.remote)
        self.profile['targets']['production']['replacement'] = {'locales': ['en-US'], 'slots': ['APP_IPHONE_65'], 'allow_delete': False}
        write_json(self.root / 'store-upload.json', self.profile)
        with self.assertRaisesRegex(ValueError, 'delet'):
            self.execute(self.plan('images'))
        self.assertFalse(self.provider.writes)

    def test_remote_revision_drift_between_preflight_and_write_blocks(self):
        def mutate(provider):
            if len(provider.reads) == 2:
                provider.remote['revision'] = 'changed concurrently'
        self.provider.on_snapshot = mutate
        with self.assertRaisesRegex(ValueError, 'snapshot|revision'):
            self.execute()
        self.assertEqual(self.provider.writes, [])

    def test_apple_active_review_blocks_listing(self):
        remote = json.loads((self.root / 'remote.json').read_text())
        remote['review_active'] = True
        write_json(self.root / 'remote.json', remote)
        self.provider.remote = remote
        with self.assertRaisesRegex(ValueError, 'review'):
            self.execute(self.plan('metadata'))
        self.assertEqual(self.provider.writes, [])

    def test_dry_run_does_not_read_store_write_or_create_attempt(self):
        self.provider.on_snapshot = lambda _: self.fail('dry-run read the provider')
        receipt = self.execute(dry_run=True)
        self.assertEqual(receipt['status'], 'dry-run')
        self.assertEqual(self.provider.writes, [])
        self.assertFalse((self.root / 'build/store-assets').exists())

    def test_wrong_digest_blocks_before_remote_lookup(self):
        plan = self.plan()
        with self.assertRaisesRegex(ValueError, 'digest'):
            self.executor.execute(self.root, plan, 'wrong', self.provider, self.root / 'build/store-assets')
        self.assertEqual(self.provider.reads, [])

    def test_native_track_status_notes_cannot_inherit_environment_defaults(self):
        self.root, self.profile = fixture(self, store='google')
        self.profile['targets']['production']['changelogs'] = {'en-US': 'metadata/en-US/changelogs/9.txt'}
        write_json(self.root / 'store-upload.json', self.profile)
        self.provider = FakeProvider(self.root)
        with patch.dict(os.environ, {'SUPPLY_TRACK': 'production', 'SUPPLY_RELEASE_STATUS': 'draft'}):
            receipt = self.execute()
        payload = self.provider.writes[0]['payload']
        self.assertEqual(payload['target']['track'], 'alpha')
        self.assertEqual(payload['release_status'], 'completed')
        self.assertEqual(payload['release_notes'], {'en-US': 'Approved notes\n'})
        self.assertIn('release-notes', payload['effects'])
        self.assertEqual(receipt['status'], 'verified')

    def test_processing_pending_is_not_verified_and_duplicate_is_blocked(self):
        self.provider.pending = True
        plan = self.plan()
        receipt = self.execute(plan)
        self.assertEqual(receipt['status'], 'accepted_pending_verification')
        with self.assertRaisesRegex(ValueError, 'attempt|pending|already'):
            self.execute(plan)
        self.assertEqual(len(self.provider.writes), 1)

    def test_alternate_state_cannot_bypass_pending_or_concurrency_guards(self):
        self.provider.pending = True
        plan = self.plan()
        self.execute(plan)
        with self.assertRaisesRegex(ValueError, 'canonical|state|pending'):
            self.executor.execute(self.root, plan, plan['digest'], self.provider, self.root / 'different-state')
        self.assertEqual(len(self.provider.writes), 1)

    def test_binary_readback_requires_actual_platform(self):
        plan = self.plan()
        report = self.provider.readback(plan, {})
        report['observed']['binary']['platform'] = 'macos'
        self.assertFalse(self.executor.readback_matches(plan['payload'], report, {}))
        del report['observed']['binary']['platform']
        self.assertFalse(self.executor.readback_matches(plan['payload'], report, {}))

    def test_null_remote_binary_is_processing_pending(self):
        self.provider.readback = lambda plan, result: {'target': plan['payload']['target'], 'observed': {'binary': None}}
        self.assertEqual(self.execute()['status'], 'accepted_pending_verification')

    def test_pending_target_blocks_changed_digest_blind_retry(self):
        self.provider.pending = True
        self.execute()
        (self.root / 'helpers/version_guard.rb').write_text('new plan, same pending target')
        with self.assertRaisesRegex(ValueError, 'pending|recovery'):
            self.execute()
        self.assertEqual(len(self.provider.writes), 1)

    def test_added_staged_helper_blocks_before_transfer(self):
        def add_helper(provider):
            staged = next((self.root / 'build/store-assets/attempts').glob('*/inputs'))
            (staged / 'helpers/extra.py').write_text('unreviewed executable')
        self.provider.on_snapshot = add_helper
        with self.assertRaisesRegex(ValueError, 'inventory|added'):
            self.execute()
        self.assertEqual(self.provider.writes, [])

    def test_staged_mutation_during_final_snapshot_blocks_before_transfer(self):
        for directory, path in (('inputs', 'helpers/provider.py'),
                                ('runtime', 'lib/store_provider.rb'),
                                ('inputs', 'helpers/unreviewed.py')):
            with self.subTest(directory=directory, path=path):
                root, _ = fixture(self)
                provider = FakeProvider(root)
                plan = self.planning.make_plan(root, 'store-upload.json', 'production', 'binary')
                state = root / 'build/store-assets'

                def mutate(provider, state=state, directory=directory, path=path):
                    if len(provider.reads) == 2:
                        staged = next((state / 'attempts').glob('*/' + directory)) / path
                        if staged.exists():
                            staged.chmod(0o644)
                        staged.write_text('# unreviewed staged replacement\n')

                provider.on_snapshot = mutate
                with self.assertRaisesRegex(ValueError, 'changed|inventory|added'):
                    self.executor.execute(root, plan, plan['digest'], provider, state)
                self.assertEqual(provider.writes, [])
                receipt = json.loads(next((state / 'attempts').glob('*/receipt.json')).read_text())
                self.assertFalse(receipt['effects_started'])
                self.assertEqual(receipt['status'], 'failed_preflight')

    def test_receipt_window_replacement_never_launches_changed_provider_code(self):
        script = self.root / 'helpers/provider.py'
        script.write_text('''import json,pathlib,sys
request=json.load(sys.stdin)
root=pathlib.Path(request['root'])
if request['action']=='snapshot':
    print((root/'remote.json').read_text())
elif request['action']=='upload':
    (root.parent/'executed-code.txt').write_text('approved')
    print(json.dumps({'accepted':True}))
else:
    print(json.dumps({}))
''')
        plan = self.plan()
        provider = module(self, 'providers').CommandProvider(
            self.profile['targets']['production'], 'fixture', allow_effects=True,
            expected_executable=plan['payload']['provider_executable'])
        original = self.executor.write_record

        def mutate(path, value):
            original(path, value)
            if path.name == 'receipt.json' and value['status'] == 'transferring':
                staged = path.parent / 'inputs'
                self.assertFalse(staged.stat().st_mode & 0o222)
                self.assertFalse((staged / 'helpers').stat().st_mode & 0o222)
                changed = staged / 'helpers/provider.py'
                changed.chmod(0o644)
                changed.write_text('import json,pathlib; pathlib.Path("../executed-code.txt").write_text("unreviewed"); print(json.dumps({"accepted":True}))\n')

        with patch.object(self.executor, 'write_record', side_effect=mutate):
            with self.assertRaisesRegex(ValueError, 'changed'):
                self.executor.execute(self.root, plan, plan['digest'], provider, self.root / 'build/store-assets')
        attempt = next((self.root / 'build/store-assets/attempts').iterdir())
        self.assertEqual((attempt / 'executed-code.txt').read_text(), 'approved')
        self.assertEqual(json.loads((attempt / 'receipt.json').read_text())['status'], 'failed_partial')

    def test_state_symlink_blocks_before_read(self):
        (self.root / 'actual-state').mkdir()
        (self.root / 'build').mkdir()
        (self.root / 'build/store-assets').symlink_to(self.root / 'actual-state', target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'symlink'):
            self.execute()
        self.assertEqual(self.provider.reads, [])

    def test_readback_preserves_unselected_public_metadata_fields(self):
        def readback(plan, result):
            return {'target': plan['payload']['target'], 'observed': {'fields': {
                'en-US': {'description': 'Approved description', 'keywords': 'preserved,remote'}}}}
        self.provider.readback = readback
        self.assertEqual(self.execute(self.plan('metadata'))['status'], 'verified')

    def test_partial_failure_retains_attempt_and_blocks_blind_retry(self):
        def fail(_):
            raise RuntimeError('synthetic failure after possible external write')
        self.provider.on_upload = fail
        plan = self.plan()
        with self.assertRaises(RuntimeError):
            self.execute(plan)
        receipts = list((self.root / 'build/store-assets/attempts').glob('*/receipt.json'))
        self.assertEqual(len(receipts), 1)
        self.assertEqual(json.loads(receipts[0].read_text())['status'], 'failed_partial')
        with self.assertRaisesRegex(ValueError, 'attempt|pending|already'):
            self.execute(plan)

    def test_concurrent_same_app_attempt_is_blocked_before_second_read(self):
        plan = self.plan()
        def nested(provider):
            if len(provider.reads) == 1:
                with self.assertRaisesRegex(ValueError, 'lock|concurrent'):
                    self.execute(plan)
        self.provider.on_snapshot = nested
        self.execute(plan)
        self.assertEqual(len(self.provider.writes), 1)


if __name__ == '__main__':
    unittest.main()
