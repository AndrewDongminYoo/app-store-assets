"""U0 read-only snapshot export against a fake App Store Connect; no gem, network or credentials."""
import copy
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from app_store_assets.catalog import validate_apple_localizations
from app_store_assets.metadata import remote_observation, validate_public_metadata

ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / 'lib/fastlane_assets.rb'
FAKE = ROOT / 'tests/fake_spaceship'
HARNESS = ROOT / 'tests/snapshot_export_harness.rb'
READS = {
    'App.find',
    'App#get_app_store_versions',
    'App#get_in_progress_review_submission',
    'App#fetch_edit_app_info',
    'AppInfo#get_app_info_localizations',
    'AppStoreVersion#get_build',
    'AppStoreVersion#get_app_store_version_localizations',
    'AppStoreVersionLocalization#get_app_screenshot_sets',
}
VERSION_FIELDS = {'description', 'keywords', 'promotional_text', 'release_notes', 'support_url', 'marketing_url'}


def target(**changes):
    value = {'store': 'apple', 'platform': 'ios', 'account': 'personal', 'account_id': 'personal-team',
             'app_id': 'com.example.kkom', 'flavor': 'prod', 'stage': 'release',
             'version': {'name': '1.2.0', 'build': '42'}}
    value.update(changes)
    return value


def shot(ident, state='COMPLETE', width=1290, height=2796):
    return {'id': ident, 'asset_delivery_state': {'state': state, 'errors': []},
            'image_asset': {'templateUrl': 'https://example.com/{w}x{h}.{f}', 'width': width, 'height': height},
            'source_file_checksum': '0' * 32, 'file_size': 12345, 'file_name': ident + '.png'}


def localization(locale, sets, **values):
    data = {'id': 'loc-' + locale, 'locale': locale, 'description': 'Description ' + locale,
            'keywords': 'cat,food', 'promotional_text': None, 'whats_new': 'Fixes',
            'support_url': 'https://example.com/support', 'marketing_url': None, 'sets': sets}
    data.update(values)
    return data


def scenario():
    return {
        'app': {
            'id': 'app-1', 'bundle_id': 'com.example.kkom', 'review_submission': False,
            'app_info': {'id': 'info-edit', 'state': 'PREPARE_FOR_SUBMISSION', 'localizations': [
                {'id': 'info-en', 'locale': 'en-US', 'name': 'Kkom', 'subtitle': None,
                 'privacy_policy_url': 'https://example.com/privacy'},
                {'id': 'info-ko', 'locale': 'ko', 'name': '꼼꼼이', 'subtitle': '기록', 'privacy_policy_url': None},
            ]},
            'versions': [{
                'id': 'version-120', 'version_string': '1.2.0', 'platform': 'IOS',
                'app_version_state': 'PREPARE_FOR_SUBMISSION', 'app_store_state': 'PREPARE_FOR_SUBMISSION',
                'build': {'id': 'build-42', 'version': '42', 'processing_state': 'VALID'},
                'localizations': [
                    localization('en-US', [
                        {'id': 'set-en-67', 'screenshot_display_type': 'APP_IPHONE_67',
                         'screenshots': [shot('shot-b'), shot('shot-a', state='UPLOAD_COMPLETE')]},
                        {'id': 'set-en-ipad', 'screenshot_display_type': 'APP_IPAD_PRO_3GEN_129',
                         'screenshots': [shot('shot-c', width=2048, height=2732)]},
                    ]),
                    localization('ko', [
                        {'id': 'set-ko-67', 'screenshot_display_type': 'APP_IPHONE_67',
                         'screenshots': [shot('shot-d')]},
                    ]),
                ],
            }],
        },
    }


def version_of(data):
    return data['app']['versions'][0]


class SnapshotExportTests(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.tmp = Path(scratch.name).resolve()
        (self.tmp / 'home').mkdir()
        self.output = self.tmp / 'out/snapshot.json'
        self.output.parent.mkdir()

    def run_export(self, data, identity=None, output=None, deadline=None, lib=LIB, load_path=FAKE, timeout=30,
                   extra_env=None):
        (self.tmp / 'scenario.json').write_text(json.dumps(data))
        log = self.tmp / 'calls.json'
        if log.exists():
            log.unlink()
        env = {'PATH': os.environ['PATH'], 'HOME': str(self.tmp / 'home'), 'LANG': 'C.UTF-8',
               'PYTHON': sys.executable, 'FAKE_ASC_SCENARIO': str(self.tmp / 'scenario.json'),
               'FAKE_ASC_LOG': str(log), **(extra_env or {})}
        command = ['ruby', '--disable-gems'] + (['-I', str(load_path)] if load_path else [])
        command += [str(HARNESS), str(lib), json.dumps(identity or target()), str(output or self.output)]
        if deadline is not None:
            command.append(str(deadline))
        result = subprocess.run(command, capture_output=True, text=True, env=env, timeout=timeout)
        calls = json.loads(log.read_text()) if log.exists() else []
        return result, calls

    def assertReadOnly(self, calls):
        self.assertEqual([c['call'] for c in calls if c['call'] not in READS], [], calls)

    def assertRefused(self, result, message, output=None):
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn('snapshot export refused', result.stderr)
        self.assertIn(message, result.stderr)
        self.assertEqual(result.stdout, '')
        output = output or self.output
        self.assertFalse(output.exists() or output.is_symlink())
        self.assertEqual(sorted(p.name for p in output.parent.iterdir() if p.name.endswith('.tmp')), [])

    def export(self, data, **options):
        result, calls = self.run_export(data, **options)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertReadOnly(calls)
        return json.loads(self.output.read_text()), result, calls

    def test_complete_record_round_trips_through_the_public_validators(self):
        record, result, calls = self.export(scenario())
        self.assertEqual(record['schema_version'], 1)
        self.assertEqual(record['type'], 'metadata-snapshot')
        self.assertEqual(record['target'], target())
        self.assertEqual((record['version_id'], record['editable'], record['review_active'], record['app_info_id']),
                         ('version-120', True, False, 'info-edit'))
        self.assertEqual(record['binary'], {'app_id': 'com.example.kkom', 'platform': 'ios',
                                            'version': {'name': '1.2.0', 'build': '42'}, 'processing_state': 'VALID'})
        validate_public_metadata(record, record['target'])
        observed = remote_observation(record)
        validate_apple_localizations({'images': {'en-US': {}, 'ko': {}}}, observed, 'images')
        # The live sample shows the planned path: the observation the planner would use is the record.
        self.assertEqual(observed, record)
        self.assertEqual(calls[1]['arguments']['filter'], {'versionString': '1.2.0', 'platform': 'IOS'})

    def test_every_version_field_is_present_even_when_empty(self):
        record, _, _ = self.export(scenario())
        for locale in ('en-US', 'ko'):
            self.assertTrue(VERSION_FIELDS <= set(record['fields'][locale]), record['fields'][locale])
        self.assertEqual(record['fields']['en-US']['promotional_text'], '')
        self.assertEqual(record['fields']['en-US']['marketing_url'], '')
        self.assertEqual(record['fields']['en-US']['release_notes'], 'Fixes')
        self.assertEqual(record['fields']['en-US']['privacy_url'], 'https://example.com/privacy')
        self.assertEqual(record['fields']['ko']['name'], '꼼꼼이')
        self.assertEqual(record['fields']['ko']['privacy_url'], '')

    def test_multiple_locales_and_display_types_keep_screenshot_order(self):
        record, result, _ = self.export(scenario())
        self.assertEqual(record['images'], {
            'en-US': {
                'APP_IPHONE_67': [
                    {'id': 'shot-b', 'processing_state': 'COMPLETE', 'width': 1290, 'height': 2796},
                    {'id': 'shot-a', 'processing_state': 'UPLOAD_COMPLETE', 'width': 1290, 'height': 2796},
                ],
                'APP_IPAD_PRO_3GEN_129': [{'id': 'shot-c', 'processing_state': 'COMPLETE', 'width': 2048, 'height': 2732}],
            },
            'ko': {'APP_IPHONE_67': [{'id': 'shot-d', 'processing_state': 'COMPLETE', 'width': 1290, 'height': 2796}]},
        })
        report = json.loads(result.stdout)
        self.assertEqual(report['counts'], {'locales': 2, 'screenshot_sets': 3, 'screenshots': 4})

    def test_image_entries_hold_only_fields_with_a_live_equivalent(self):
        data = scenario()
        version_of(data)['localizations'][1]['sets'][0]['screenshots'] = [
            {'id': 'shot-unknown', 'asset_delivery_state': None, 'image_asset': None}]
        record, _, _ = self.export(data)
        for groups in record['images'].values():
            for images in groups.values():
                for image in images:
                    self.assertLessEqual(set(image), {'id', 'processing_state', 'width', 'height'})
        self.assertEqual(record['images']['ko']['APP_IPHONE_67'], [{'id': 'shot-unknown'}])

    def test_standard_output_is_one_result_with_the_record_hash(self):
        data = scenario()
        data['print'] = True
        _, result, _ = self.export(data)
        self.assertEqual(result.stdout.count('\n'), 1, result.stdout)
        report = json.loads(result.stdout)
        self.assertEqual(report['output'], str(self.output))
        self.assertEqual(report['sha256'], hashlib.sha256(self.output.read_bytes()).hexdigest())
        self.assertIn('fake provider output from App.find', result.stderr)

    def test_verbose_request_logger_writes_to_standard_error(self):
        # Spaceship's VERBOSE logger holds STDOUT itself, and may be built before the export, at login.
        for preload in (False, True):
            with self.subTest(preload=preload):
                if self.output.exists():
                    self.output.unlink()
                extra_env = {'VERBOSE': '1', **({'FAKE_ASC_PRELOAD': '1'} if preload else {})}
                _, result, _ = self.export(scenario(), extra_env=extra_env)
                self.assertEqual(result.stdout.count('\n'), 1, result.stdout)
                self.assertEqual(json.loads(result.stdout)['output'], str(self.output))
                self.assertIn('>> GET App.find', result.stderr)

    def test_version_that_is_not_editable_is_recorded_as_such(self):
        for state in ('READY_FOR_DISTRIBUTION', 'PENDING_DEVELOPER_RELEASE', None):
            with self.subTest(state=state):
                if self.output.exists():
                    self.output.unlink()
                data = scenario()
                version_of(data).update(app_version_state=state, app_store_state=None)
                record, _, _ = self.export(data)
                self.assertIs(record['editable'], False)
                validate_public_metadata(record, record['target'])
                with self.assertRaisesRegex(ValueError, 'editable'):
                    validate_apple_localizations({'images': {'en-US': {}}}, remote_observation(record), 'images')

    def test_review_in_progress_is_recorded_as_active(self):
        cases = [({'review_submission': True}, {}, True),
                 ({}, {'app_version_state': 'WAITING_FOR_REVIEW'}, False)]
        for app_changes, version_changes, editable in cases:
            with self.subTest(app=app_changes, version=version_changes):
                if self.output.exists():
                    self.output.unlink()
                data = scenario()
                data['app'].update(app_changes)
                version_of(data).update(version_changes)
                record, _, calls = self.export(data)
                self.assertIs(record['review_active'], True)
                self.assertIs(record['editable'], editable)
                self.assertIn({'call': 'App#get_in_progress_review_submission', 'arguments': {'platform': 'IOS'}}, calls)
                with self.assertRaisesRegex(ValueError, 'no active review'):
                    validate_apple_localizations({'images': {'en-US': {}}}, remote_observation(record), 'images')

    def test_no_editable_app_info_records_no_app_info_fields(self):
        data = scenario()
        data['app']['app_info'] = None
        record, _, calls = self.export(data)
        self.assertIsNone(record['app_info_id'])
        for values in record['fields'].values():
            self.assertEqual(set(values), VERSION_FIELDS)
        validate_public_metadata(record, record['target'])
        validate_apple_localizations({'images': {'en-US': {}}}, remote_observation(record), 'images')
        self.assertNotIn('AppInfo#get_app_info_localizations', [c['call'] for c in calls])

    def test_app_info_waiting_for_review_is_not_recorded_as_editable(self):
        # fastlane's fetch_edit_app_info also returns this app info; it accepts no edit.
        for state in ('WAITING_FOR_REVIEW', None):
            with self.subTest(state=state):
                if self.output.exists():
                    self.output.unlink()
                data = scenario()
                data['app']['app_info']['state'] = state
                record, _, calls = self.export(data)
                self.assertIsNone(record['app_info_id'])
                for values in record['fields'].values():
                    self.assertEqual(set(values), VERSION_FIELDS)
                self.assertIn('App#fetch_edit_app_info', [c['call'] for c in calls])
                self.assertNotIn('AppInfo#get_app_info_localizations', [c['call'] for c in calls])
                with self.assertRaisesRegex(ValueError, 'exact editable app-info snapshot required'):
                    validate_apple_localizations({'fields': {'en-US': {'name': 'Kkom'}}},
                                                 remote_observation(record), 'metadata')

    def test_version_without_an_id_is_refused(self):
        for ident in (None, ''):
            with self.subTest(ident=ident):
                data = scenario()
                version_of(data)['id'] = ident
                result, calls = self.run_export(data)
                self.assertRefused(result, 'App Store version 1.2.0 has no ID')
                self.assertReadOnly(calls)

    def test_no_attached_build_records_no_binary(self):
        data = scenario()
        version_of(data)['build'] = None
        record, _, _ = self.export(data)
        self.assertNotIn('binary', record)
        remote_observation(record)

    def test_other_build_lookup_errors_are_not_read_as_no_build(self):
        # Only Spaceship's exact "No data" means that no build is attached.
        data = scenario()
        version_of(data)['build_error'] = 'Server error got 500'
        result, calls = self.run_export(data)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Server error got 500', result.stderr)
        self.assertFalse(self.output.exists())
        self.assertReadOnly(calls)

    def test_attached_build_that_differs_from_the_target_is_refused(self):
        for build in ({'version': '41', 'processing_state': 'VALID'}, {'version': '42', 'processing_state': None}):
            with self.subTest(build=build):
                data = scenario()
                version_of(data)['build'] = build
                result, calls = self.run_export(data)
                self.assertRefused(result, 'attached build')
                self.assertReadOnly(calls)

    def test_missing_app_is_refused(self):
        data = scenario()
        data['app']['bundle_id'] = 'com.example.other'
        result, calls = self.run_export(data)
        self.assertRefused(result, 'no App Store Connect app for com.example.kkom')
        self.assertEqual([c['call'] for c in calls], ['App.find'])

    def test_missing_or_ambiguous_version_is_refused(self):
        data = scenario()
        version_of(data)['version_string'] = '1.1.0'
        result, calls = self.run_export(data)
        self.assertRefused(result, 'no iOS App Store version 1.2.0')
        self.assertReadOnly(calls)

        # The selection is re-checked even when the provider ignores the filter.
        data = scenario()
        data['ignore_filter'] = True
        other = copy.deepcopy(version_of(data))
        other.update(id='version-mac', platform='MAC_OS')
        older = copy.deepcopy(version_of(data))
        older.update(id='version-110', version_string='1.1.0')
        data['app']['versions'] += [other, older]
        record, _, _ = self.export(data)
        self.assertEqual(record['version_id'], 'version-120')

        self.output.unlink()
        data['app']['versions'].append(dict(copy.deepcopy(version_of(data)), id='version-120b'))
        result, calls = self.run_export(data)
        self.assertRefused(result, 'more than one iOS App Store version')
        self.assertReadOnly(calls)

    def test_empty_and_absent_screenshot_sets_stay_distinct(self):
        data = scenario()
        en, ko = version_of(data)['localizations']
        en['sets'] = [{'id': 'set-en-67', 'screenshot_display_type': 'APP_IPHONE_67', 'screenshots': []}]
        ko['sets'] = []
        record, result, _ = self.export(data)
        self.assertEqual(record['images'], {'en-US': {'APP_IPHONE_67': []}, 'ko': {}})
        self.assertEqual(json.loads(result.stdout)['counts'], {'locales': 2, 'screenshot_sets': 1, 'screenshots': 0})
        remote_observation(record)

    def test_duplicate_provider_entries_are_refused(self):
        # Without the guard the second entry silently overwrites the first.
        def duplicate_set(data):
            en = version_of(data)['localizations'][0]
            en['sets'].append(copy.deepcopy(en['sets'][0]))

        def duplicate_info(data):
            infos = data['app']['app_info']['localizations']
            infos.append(dict(copy.deepcopy(infos[0]), id='info-en-2', name='Other'))

        def duplicate_version_locale(data):
            localizations = version_of(data)['localizations']
            localizations.append(dict(copy.deepcopy(localizations[0]), id='loc-en-US-2', sets=[]))

        cases = [(duplicate_set, 'duplicate screenshot set en-US/APP_IPHONE_67'),
                 (duplicate_info, 'duplicate app info locale en-US'),
                 (duplicate_version_locale, 'duplicate version locale en-US')]
        for change, message in cases:
            with self.subTest(message=message):
                data = scenario()
                change(data)
                result, calls = self.run_export(data)
                self.assertRefused(result, message)
                self.assertReadOnly(calls)

    def test_full_provider_pages_are_refused_as_truncated(self):
        def full_version_localizations(data):
            version_of(data)['localizations'] = [localization(f'en-X{i:03d}', []) for i in range(200)]

        def full_info_localizations(data):
            data['app']['app_info']['localizations'] = [
                {'id': f'info-{i}', 'locale': f'en-X{i:03d}', 'name': 'Kkom', 'subtitle': None,
                 'privacy_policy_url': None} for i in range(200)]

        def full_screenshot_sets(data):
            # Distinct display types, so that only the page guard can refuse them.
            version_of(data)['localizations'][0]['sets'] = [
                {'id': f'set-{i}', 'screenshot_display_type': f'APP_TYPE_{i:03d}', 'screenshots': []}
                for i in range(200)]

        cases = [(full_version_localizations, 'version localizations returned a full page',
                  {'call': 'AppStoreVersion#get_app_store_version_localizations', 'arguments': {'limit': 200}}),
                 (full_info_localizations, 'app info localizations returned a full page',
                  {'call': 'AppInfo#get_app_info_localizations', 'arguments': {'limit': 200}}),
                 (full_screenshot_sets, 'screenshot sets en-US returned a full page',
                  {'call': 'AppStoreVersionLocalization#get_app_screenshot_sets',
                   'arguments': {'locale': 'en-US', 'limit': 200}})]
        for change, message, call in cases:
            with self.subTest(message=message):
                data = scenario()
                change(data)
                result, calls = self.run_export(data)
                self.assertRefused(result, message)
                self.assertIn(call, calls)
                self.assertReadOnly(calls)

    def test_existing_output_is_refused_before_any_provider_call(self):
        self.output.write_text('keep')
        result, calls = self.run_export(scenario())
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('output already exists', result.stderr)
        self.assertEqual(calls, [])
        self.assertEqual(self.output.read_text(), 'keep')

        self.output.unlink()
        self.output.symlink_to(self.tmp / 'missing-target.json')
        result, calls = self.run_export(scenario())
        self.assertIn('output already exists', result.stderr)
        self.assertEqual(calls, [])
        self.assertFalse((self.tmp / 'missing-target.json').exists())

    def test_output_created_during_the_read_is_never_replaced(self):
        data = scenario()
        data['create_output'] = {'during': 'AppStoreVersion#get_build', 'path': str(self.output), 'content': 'other'}
        result, calls = self.run_export(data)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('output already exists', result.stderr)
        self.assertEqual(self.output.read_text(), 'other')
        self.assertEqual([p.name for p in self.output.parent.iterdir()], ['snapshot.json'])
        self.assertReadOnly(calls)

    def test_output_directory_replaced_during_the_read_receives_nothing(self):
        # Without the identity check, the record would land in the replacement directory.
        replacement = self.tmp / 'elsewhere'
        replacement.mkdir()
        moved = self.tmp / 'out-moved'
        data = scenario()
        data['swap_directory'] = {'during': 'AppStoreVersion#get_build', 'path': str(self.output.parent),
                                  'moved_to': str(moved), 'replacement': str(replacement)}
        result, calls = self.run_export(data)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('snapshot export refused: output directory changed during the export', result.stderr)
        self.assertEqual(result.stdout, '')
        self.assertEqual(list(replacement.iterdir()), [])
        self.assertEqual(list(moved.iterdir()), [])
        self.assertReadOnly(calls)

    def test_long_output_name_is_published(self):
        # A temporary name built from the output name would exceed the 255-byte name limit.
        output = self.output.parent / ('s' * 250 + '.json')
        result, calls = self.run_export(scenario(), output=output)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['output'], str(output))
        self.assertEqual([p.name for p in output.parent.iterdir()], [output.name])
        self.assertReadOnly(calls)

    def runtime_copy(self):
        runtime = self.tmp / 'runtime'
        (runtime / 'lib').mkdir(parents=True)
        shutil.copyfile(LIB, runtime / 'lib/fastlane_assets.rb')
        shutil.copytree(ROOT / 'app_store_assets', runtime / 'app_store_assets',
                        ignore=shutil.ignore_patterns('__pycache__'))
        shutil.copytree(ROOT / 'catalog', runtime / 'catalog')
        return runtime

    def test_output_inside_the_runtime_checkout_is_refused(self):
        runtime = self.runtime_copy()
        (self.tmp / 'link-to-runtime').symlink_to(runtime / 'lib')
        for output in (runtime / 'snapshot.json', runtime / 'catalog/snapshot.json',
                       self.tmp / 'link-to-runtime/snapshot.json'):
            with self.subTest(output=output):
                result, calls = self.run_export(scenario(), output=output, lib=runtime / 'lib/fastlane_assets.rb')
                self.assertRefused(result, 'outside the app-store-assets checkout', output=output)
                self.assertEqual(calls, [])

    def test_runtime_checkout_stays_clean_after_an_export(self):
        runtime = self.runtime_copy()
        before = sorted(str(p.relative_to(runtime)) for p in runtime.rglob('*'))
        result, calls = self.run_export(scenario(), lib=runtime / 'lib/fastlane_assets.rb')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertReadOnly(calls)
        self.assertEqual(sorted(str(p.relative_to(runtime)) for p in runtime.rglob('*')), before)
        remote_observation(json.loads(self.output.read_text()))

    def test_output_path_must_be_absolute_with_an_existing_directory(self):
        for output, message in (('relative/snapshot.json', 'absolute path'),
                                (str(self.tmp / 'absent/snapshot.json'), 'does not exist')):
            with self.subTest(output=output):
                result, calls = self.run_export(scenario(), output=output)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(message, result.stderr)
                self.assertEqual(calls, [])
        self.assertFalse((self.tmp / 'absent').exists())

    def test_output_parent_that_is_a_regular_file_is_refused_before_any_provider_call(self):
        parent = self.tmp / 'out/regular-file'
        parent.write_text('keep')
        output = parent / 'snapshot.json'
        result, calls = self.run_export(scenario(), output=output)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('snapshot export refused: output directory is not a directory', result.stderr)
        self.assertEqual(calls, [])
        self.assertEqual(parent.read_text(), 'keep')

    def test_publish_failure_other_than_an_existing_output_is_refused(self):
        # A filesystem without hard links: the export refuses and leaves no file behind.
        data = scenario()
        data['link_error'] = 'EPERM'
        result, calls = self.run_export(data)
        self.assertRefused(result, 'could not publish')
        self.assertIn('hard link: EPERM', result.stderr)
        self.assertReadOnly(calls)
        self.assertEqual(list(self.output.parent.iterdir()), [])

    def test_unsupported_target_is_refused_before_any_provider_call(self):
        cases = [
            (target(store='google', platform='android', track='production'), 'unknown target keys: track'),
            (target(store='google', platform='android'), 'only store apple with platform ios'),
            (target(platform='macos'), 'only store apple with platform ios'),
            (dict(target(), remote='snapshot.json'), 'unknown target keys: remote'),
            ({k: v for k, v in target().items() if k != 'stage'}, 'missing target keys: stage'),
            (target(version={'name': '1.2.0'}), 'numeric name and build'),
            (target(app_id='com.example/kkom'), 'app_id must be a bundle identifier'),
            (target(app_id=['com.example.kkom']), 'app_id must be a bundle identifier'),
            # A non-empty list: run_export replaces a falsy identity with the default target.
            (['com.example.kkom'], 'target must be a hash'),
            ('com.example.kkom', 'target must be a hash'),
        ]
        for identity, message in cases:
            with self.subTest(message=message):
                result, calls = self.run_export(scenario(), identity=identity)
                self.assertRefused(result, message)
                self.assertEqual(calls, [])

    def test_malformed_identity_fields_are_refused_before_any_provider_call(self):
        # Without the up-front identity validation, these reach every provider read first.
        cases = [dict(target(), account=None), dict(target(), flavor=''), dict(target(), stage='bad\nstage'),
                 dict(target(), account_id='')]
        for identity in cases:
            with self.subTest(identity=identity):
                result, calls = self.run_export(scenario(), identity=identity)
                self.assertRefused(result, 'target fails the identity validator')
                self.assertEqual(calls, [])

    def test_target_without_an_account_id_is_recorded_unchanged(self):
        identity = {k: v for k, v in target().items() if k != 'account_id'}
        record, _, _ = self.export(scenario(), identity=identity)
        self.assertEqual(record['target'], identity)
        validate_public_metadata(record, identity)

    def test_provider_call_that_keeps_retrying_fails_at_the_deadline(self):
        data = scenario()
        data['hang'] = {'call': 'AppStoreVersion#get_build', 'seconds': 20}
        started = time.monotonic()
        result, calls = self.run_export(data, deadline=0.5, timeout=15)
        self.assertLess(time.monotonic() - started, 10)
        self.assertRefused(result, 'deadline: attached build')
        self.assertReadOnly(calls)

    def test_deadline_has_an_upper_bound(self):
        for deadline in (0, 601):
            with self.subTest(deadline=deadline):
                result, calls = self.run_export(scenario(), deadline=deadline)
                self.assertRefused(result, 'deadline must be')
                self.assertEqual(calls, [])

    def test_record_that_fails_the_validators_is_never_written(self):
        cases = [('marketing_url', 'https://user:secret@example.com/'),
                 ('promotional_text', 'x' * 171),
                 ('support_url', 'https://example.com/?token=abc')]
        for key, value in cases:
            with self.subTest(key=key):
                data = scenario()
                version_of(data)['localizations'][0][key] = value
                result, calls = self.run_export(data)
                self.assertRefused(result, 'fails the public metadata validators')
                self.assertNotIn('secret', result.stderr)
                self.assertReadOnly(calls)

    def test_loading_the_library_needs_no_spaceship(self):
        code = 'require ARGV.fetch(0); puts defined?(Spaceship).inspect'
        result = subprocess.run(['ruby', '--disable-gems', '-e', code, str(LIB)],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), 'nil')
        result, _ = self.run_export(scenario(), load_path=None)
        self.assertRefused(result, 'Spaceship is unavailable')

    def test_legacy_prepare_stays_blocked(self):
        code = 'require ARGV.fetch(0); begin; AppStoreAssets.prepare; rescue => e; puts e.message; end'
        result = subprocess.run(['ruby', '--disable-gems', '-e', code, str(LIB)],
                                capture_output=True, text=True, timeout=30)
        self.assertIn('reviewed plan', result.stdout)


if __name__ == '__main__':
    unittest.main()
