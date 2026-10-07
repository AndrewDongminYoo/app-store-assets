"""Offline store field support and complete image readback contracts."""
import copy
import hashlib
import json
import unittest

from pipeline_support import ROOT, fixture, module, write_json
from test_assets import png
from test_execution import FakeProvider


class StoreBoundaryTests(unittest.TestCase):
    def test_cross_store_fields_are_rejected_during_planning(self):
        for store, field in (('apple', 'title'), ('apple', 'video'), ('google', 'keywords'),
                             ('google', 'subtitle'), ('apple', 'copyright')):
            with self.subTest(store=store, field=field):
                root, profile = fixture(self, store=store)
                path = root / 'metadata/listing.json'
                listing = json.loads(path.read_text())
                listing['fields'] = {'en-US': {field: 'public but unsupported'}}
                write_json(path, listing)
                with self.assertRaisesRegex(ValueError, 'unsupported.*field'):
                    module(self, 'planning').make_plan(root, 'store-upload.json', 'production', 'metadata')
                self.assertFalse((root / 'build/store-assets').exists())

    def test_image_readback_rejects_added_nonempty_locale_or_class(self):
        executor = module(self, 'execution')
        target = {'app_id': 'com.example.synthetic'}
        expected = {'en-US': {'APP_IPHONE_65': [{'sha256': 'approved-image'}]}}
        payload = {'target': target, 'operation': 'images', 'listing': {'images': expected}}
        actual = {'en-US': {'APP_IPHONE_65': [{'source_sha256': 'approved-image', 'processing_state': 'processed'}]}}
        report = {'target': target, 'observed': {'images': actual}}
        self.assertTrue(executor.readback_matches(payload, report, {}))
        for locale, slot in (('en-US', 'APP_IPAD_PRO_129'), ('de-DE', 'APP_IPHONE_65')):
            with self.subTest(locale=locale, slot=slot):
                changed = copy.deepcopy(report)
                changed['observed']['images'].setdefault(locale, {})[slot] = [{'id': 'concurrent-image'}]
                self.assertFalse(executor.readback_matches(payload, changed, {}))
        empty = copy.deepcopy(report)
        empty['observed']['images']['de-DE'] = {'APP_IPAD_PRO_129': []}
        self.assertTrue(executor.readback_matches(payload, empty, {}))

    def test_concurrent_image_group_keeps_receipt_pending_and_blocks_retry(self):
        root, profile = fixture(self)
        (root / 'images').mkdir()
        data = png()
        (root / 'images/01.png').write_bytes(data)
        listing = json.loads((root / 'metadata/listing.json').read_text())
        digest = hashlib.sha256(data).hexdigest()
        listing['images'] = {'en-US': {'APP_IPHONE_65': [{'file': 'images/01.png', 'sha256': digest}]}}
        write_json(root / 'metadata/listing.json', listing)
        profile['targets']['production']['replacement'] = {
            'locales': ['en-US'], 'slots': ['APP_IPHONE_65'], 'allow_delete': False}
        write_json(root / 'store-upload.json', profile)
        plan = module(self, 'planning').make_plan(root, 'store-upload.json', 'production', 'images')
        provider = FakeProvider(root)
        provider.readback = lambda plan, result: {'target': plan['payload']['target'], 'observed': {'images': {
            'en-US': {'APP_IPHONE_65': [{'source_sha256': digest, 'processing_state': 'processed'}]},
            'de-DE': {'APP_IPHONE_65': [{'id': 'concurrent-image'}]}}}}
        executor = module(self, 'execution')
        state = root / 'build/store-assets'
        receipt = executor.execute(root, plan, plan['digest'], provider, state)
        self.assertEqual(receipt['status'], 'accepted_pending_verification')
        with self.assertRaisesRegex(ValueError, 'pending|partial|recovery'):
            executor.execute(root, plan, plan['digest'], provider, state)
        self.assertEqual(len(provider.writes), 1)

    def test_catalog_field_support_matches_actual_native_adapter_constants(self):
        commands = module(self, 'commands')
        root, profile = fixture(self)
        source = ROOT / 'lib/store_provider.rb'
        script = 'require "json"; require ARGV.fetch(0); puts JSON.generate({"apple" => (StoreProvider::Apple::VERSION_FIELDS.keys + StoreProvider::Apple::INFO_FIELDS.keys).sort, "google" => StoreProvider::Google::METADATA_FIELDS.sort})'
        actual = commands.run_command(['ruby', '-e', script, str(source)], {}, root, root / 'ruby-home')
        rules = module(self, 'catalog').rules()['stores']
        for store in ('apple', 'google'):
            self.assertEqual(sorted(rules[store]['supported_fields']), actual[store])


if __name__ == '__main__':
    unittest.main()
