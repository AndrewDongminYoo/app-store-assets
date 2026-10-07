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
