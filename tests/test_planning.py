import copy
import json
import unittest
from unittest.mock import patch

from pipeline_support import fixture, module, write_json


class PlanningTests(unittest.TestCase):
    def setUp(self):
        self.planning = module(self, 'planning')
        self.root, self.profile = fixture(self)

    def plan(self, operation='binary'):
        return self.planning.make_plan(self.root, 'store-upload.json', 'production', operation)

    def test_fastfile_guard_and_changelog_changes_invalidate_approval(self):
        for path in ('helpers/Fastfile', 'helpers/version_guard.rb', 'metadata/en-US/changelogs/9.txt'):
            with self.subTest(path=path):
                plan = self.plan()
                file = self.root / path
                original = file.read_bytes()
                file.write_bytes(original + b' changed')
                try:
                    self.assertNotEqual(plan['digest'], self.plan()['digest'])
                    with self.assertRaisesRegex(ValueError, 'changed|differs'):
                        self.planning.verify_plan(self.root, plan)
                finally:
                    file.write_bytes(original)

    def test_new_transitive_helper_invalidates_approval(self):
        plan = self.plan()
        (self.root / 'helpers/new_guard.rb').write_text('new runtime dependency')
        with self.assertRaisesRegex(ValueError, 'changed|differs'):
            self.planning.verify_plan(self.root, plan)

    def test_whole_runtime_mutation_is_rejected(self):
        plan = self.plan()
        runtime = self.root / self.profile['runtime']['path']
        (runtime / 'lib/fastlane_assets.rb').write_text('changed runtime options')
        with self.assertRaisesRegex(ValueError, 'runtime'):
            self.planning.verify_plan(self.root, plan)

    def test_added_executable_runtime_input_is_rejected(self):
        (self.root / self.profile['runtime']['path'] / 'lib/unbound.rb').write_text('new executable')
        with self.assertRaisesRegex(ValueError, 'runtime'):
            self.plan()

    def test_ignored_root_bytecode_cache_cannot_override_source(self):
        runtime = self.root / self.profile['runtime']['path']
        (runtime / '__pycache__').mkdir()
        (runtime / '__pycache__/assets.cpython-314.pyc').write_bytes(b'unreviewed cache')
        with self.assertRaisesRegex(ValueError, 'bytecode|runtime'):
            self.plan()

    def test_version_types_and_empty_values_fail_closed(self):
        for value in ({'name': '', 'build': '9'}, {'name': '1.0', 'build': 9}, {'name': '1.0', 'build': '9;echo'}):
            self.profile['targets']['production']['version'] = value
            write_json(self.root / 'store-upload.json', self.profile)
            with self.assertRaisesRegex(ValueError, 'version'):
                module(self, 'profiles').load_profile(self.root, 'store-upload.json', 'production')

    def test_inspected_record_without_native_source_evidence_blocks_live(self):
        self.profile['mode'] = 'live'
        write_json(self.root / 'store-upload.json', self.profile)
        record = json.loads((self.root / 'artifact.json').read_text())
        write_json(self.root / 'artifact.json', dict(record, evidence='inspected'))
        with self.assertRaisesRegex(ValueError, 'source|guard|inspection'):
            self.plan()

    def test_google_changelog_locale_keys_fail_offline_before_provider_launch(self):
        root, profile = fixture(self, store='google')
        for locale in ('bad locale', '', '../en-US', 'en_US', 'en-US\n'):
            with self.subTest(locale=locale):
                profile['targets']['production']['changelogs'] = {locale: 'metadata/en-US/changelogs/9.txt'}
                write_json(root / 'store-upload.json', profile)
                with self.assertRaisesRegex(ValueError, 'locale'):
                    self.planning.make_plan(root, 'store-upload.json', 'production', 'binary')
        for locale in ('en-US', 'ko-KR', 'es-419'):
            profile['targets']['production']['changelogs'] = {locale: 'metadata/en-US/changelogs/9.txt'}
            write_json(root / 'store-upload.json', profile)
            plan = self.planning.make_plan(root, 'store-upload.json', 'production', 'binary')
            self.assertEqual(set(plan['payload']['release_notes']), {locale})

    def test_apple_metadata_rejects_unavailable_version_and_info_locales_offline(self):
        for fields, changes in [({'ko-KR':{'description':'approved'}},{}),
                                ({'en-US':{'name':'approved'}},{}),
                                ({'en-US':{'name':'approved'}},{'app_info_id':'exact-info'})]:
            with self.subTest(fields=fields, changes=changes):
                listing = json.loads((self.root / 'metadata/listing.json').read_text())
                listing['fields'] = fields
                write_json(self.root / 'metadata/listing.json', listing)
                remote = json.loads((self.root / 'remote.json').read_text())
                remote.update(changes)
                write_json(self.root / 'remote.json', remote)
                with self.assertRaisesRegex(ValueError, 'locale|app.info'):
                    self.plan('metadata')

    def test_apple_release_notes_limit_counts_unicode_characters_offline(self):
        for character in ['a','한','😀']:
            listing = json.loads((self.root / 'metadata/listing.json').read_text())
            listing['fields'] = {'en-US':{'release_notes':character*4001}}
            write_json(self.root / 'metadata/listing.json', listing)
            with self.subTest(character=character), self.assertRaisesRegex(ValueError, 'limit.*release_notes'):
                self.plan('metadata')
            listing['fields']['en-US']['release_notes'] = character*4000
            write_json(self.root / 'metadata/listing.json', listing)
            self.assertEqual(self.plan('metadata')['payload']['listing']['fields']['en-US']['release_notes'], character*4000)

    def test_existing_selected_binary_is_rejected_offline_for_both_stores(self):
        for store in ['apple', 'google']:
            root, profile = fixture(self, store=store)
            remote = json.loads((root/'remote.json').read_text())
            for state in ['pending', 'processed']:
                if store == 'apple':
                    remote['binary'] = dict(profile['targets']['production']['version'], processing_state=state)
                else:
                    remote['build_exists'] = True
                write_json(root/'remote.json', remote)
                with self.subTest(store=store, state=state), self.assertRaisesRegex(ValueError, 'already exists|existing.*build'):
                    self.planning.make_plan(root, 'store-upload.json', 'production', 'binary')
            remote.update(binary=None, build_exists=False)
            write_json(root/'remote.json', remote)
            self.assertEqual(self.planning.make_plan(root, 'store-upload.json', 'production', 'binary')['payload']['operation'], 'binary')

    def test_apple_binary_notes_are_rejected_before_plan_publication(self):
        self.profile['targets']['production']['changelogs'] = {'en-US': 'metadata/en-US/changelogs/9.txt'}
        write_json(self.root / 'store-upload.json', self.profile)
        with self.assertRaisesRegex(ValueError, 'Apple binary.*notes'):
            self.plan()

    def test_google_binary_unicode_notes_limit_is_per_locale(self):
        root, profile = fixture(self, store='google')
        profile['targets']['production']['changelogs'] = {'ko-KR': 'metadata/ko-KR/changelogs/9.txt',
                                                         'en-US': 'metadata/en-US/changelogs/9.txt'}
        write_json(root / 'store-upload.json', profile)
        path = root / 'metadata/ko-KR/changelogs/9.txt'
        path.parent.mkdir(parents=True)
        for count in (499, 500, 501):
            with self.subTest(count=count):
                path.write_text('한' * count)
                if count <= 500:
                    plan = self.planning.make_plan(root, 'store-upload.json', 'production', 'binary')
                    self.assertEqual(plan['payload']['release_notes']['ko-KR'], '한' * count)
                else:
                    with self.assertRaisesRegex(ValueError, 'release.notes.*limit'):
                        self.planning.make_plan(root, 'store-upload.json', 'production', 'binary')

    def test_google_version_named_changelog_must_match_build(self):
        root, profile = fixture(self, store='google')
        profile['targets']['production']['changelogs'] = {'en-US': 'metadata/en-US/changelogs/8.txt'}
        write_json(root / 'store-upload.json', profile)
        with self.assertRaisesRegex(ValueError, 'changelog|version'):
            module(self, 'profiles').load_profile(root, 'store-upload.json', 'production')

    def test_artifact_native_identity_must_agree_with_selected_target(self):
        record = json.loads((self.root / 'artifact.json').read_text())
        for key, value in [('app_id', 'com.example.other'), ('flavor', 'staging'),
                           ('version', {'name': '2.0', 'build': '10'})]:
            with self.subTest(key=key):
                changed = dict(record, **{key: value})
                write_json(self.root / 'artifact.json', changed)
                with self.assertRaisesRegex(ValueError, 'artifact|build'):
                    self.plan()
        write_json(self.root / 'artifact.json', record)

    def test_unknown_profile_key_fails_closed(self):
        write_json(self.root / 'store-upload.json', dict(self.profile, approved_runtime_comit='typo'))
        with self.assertRaisesRegex(ValueError, 'unknown'):
            self.plan()

    def test_google_description_alias_is_canonical_before_approval_and_readback(self):
        root, profile = fixture(self, store='google')
        plan = self.planning.make_plan(root, 'store-upload.json', 'production', 'metadata')
        self.assertEqual(plan['payload']['listing']['fields']['en-US'], {'full_description': 'Approved description'})
        report = {'target': plan['payload']['target'], 'observed': {'fields': {
            'en-US': {'full_description': 'Approved description'}}}}
        self.assertTrue(module(self, 'execution').readback_matches(plan['payload'], report, {}))
        listing = json.loads((root / 'metadata/listing.json').read_text())
        listing['fields']['en-US']['full_description'] = 'conflicting text'
        write_json(root / 'metadata/listing.json', listing)
        with self.assertRaisesRegex(ValueError, 'alias|conflict'):
            self.planning.make_plan(root, 'store-upload.json', 'production', 'metadata')

    def test_symlink_or_parent_escape_is_rejected(self):
        target = self.profile['targets']['production']
        for path in ('../outside', '/tmp/outside'):
            target['inputs'] = [path]
            write_json(self.root / 'store-upload.json', self.profile)
            with self.assertRaisesRegex(ValueError, 'path|relative|escape'):
                self.plan()
        target['inputs'] = ['helpers']
        (self.root / 'helpers/escape').symlink_to('/etc/hosts')
        write_json(self.root / 'store-upload.json', self.profile)
        with self.assertRaisesRegex(ValueError, 'symlink'):
            self.plan()

    def test_plan_is_offline_and_stable_across_spaces_and_shell_characters(self):
        with patch('socket.socket', side_effect=AssertionError('network forbidden')):
            plan = self.plan()
            self.assertEqual(plan, self.plan())
            self.planning.verify_plan(self.root, plan)
        self.assertEqual(plan['payload']['target']['app_id'], 'com.example.fixture')
        self.assertEqual(plan['payload']['operation'], 'binary')

    def test_development_store_binary_is_blocked(self):
        self.profile['targets']['production']['stage'] = 'development'
        write_json(self.root / 'store-upload.json', self.profile)
        with self.assertRaisesRegex(ValueError, 'development'):
            self.plan()

    def test_edited_plan_cannot_keep_original_digest(self):
        plan = self.plan()
        changed = copy.deepcopy(plan)
        changed['payload']['target']['app_id'] = 'com.example.other'
        with self.assertRaisesRegex(ValueError, 'digest'):
            self.planning.verify_plan(self.root, changed)


if __name__ == '__main__':
    unittest.main()
