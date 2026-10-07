import copy
import hashlib
import json
import unittest
import sys
from unittest.mock import patch

from pipeline_support import fixture, module, write_json
from test_assets import png


class GenerationTests(unittest.TestCase):
    def setUp(self):
        self.generation = module(self, 'generation')
        self.catalog = module(self, 'catalog')
        self.snapshots = module(self, 'snapshots')
        self.root, self.profile = fixture(self)
        (self.root / 'captures').mkdir()
        (self.root / 'captures/01.png').write_bytes(png(alpha=True))
        self.recipe = {'schema_version': 1, 'target': self.profile['targets']['production'],
                       'inputs': ['captures', 'helpers'], 'toolchain': self.generation.toolchain(),
                       'provenance': {'status': 'widget-rendered'}, 'normalize_alpha': True,
                       'outputs': [{'source': 'captures/01.png', 'file': 'images/en-US/01.png',
                                    'locale': 'en-US', 'slot': 'APP_IPHONE_65'}]}

    def generate(self, recipe=None):
        return self.generation.generate(self.root, recipe or self.recipe, self.root / 'history')

    def test_generation_is_reproducible_and_preserves_capture_provenance(self):
        original = (self.root / 'captures/01.png').read_bytes()
        a = self.generate()
        b = self.generate()
        self.assertEqual(a, b)
        record = self.snapshots.validate_snapshot(a)['record']
        self.assertEqual(record['provenance'], {'status': 'widget-rendered'})
        self.assertEqual((self.root / 'captures/01.png').read_bytes(), original)
        self.assertEqual((a / 'images/en-US/01.png').read_bytes()[25], 2)
        self.assertEqual(record['assets'][0]['sha256'], hashlib.sha256((a / 'images/en-US/01.png').read_bytes()).hexdigest())

    def test_changed_source_or_helper_produces_distinct_generation_identity(self):
        first = self.generate()
        (self.root / 'helpers/version_guard.rb').write_text('changed declared helper')
        self.assertNotEqual(first, self.generate())
        (self.root / 'captures/01.png').write_bytes(png(1284, 2778))
        self.assertNotEqual(first, self.generate())

    def test_different_toolchain_requires_new_lock(self):
        recipe = copy.deepcopy(self.recipe)
        recipe['toolchain']['magick']['version'] = 'different encoder'
        with self.assertRaisesRegex(ValueError, 'toolchain'):
            self.generate(recipe)

    def test_app_owned_composer_uses_staged_inputs_and_is_bound(self):
        helper = self.root / 'helpers/composer.py'
        helper.write_text('''import json,pathlib,sys,shutil,os
r=json.load(sys.stdin)
assert not os.environ.get('FASTLANE_PASSWORD')
p=pathlib.Path(r['output'])/'composed.png'
shutil.copyfile(pathlib.Path(r['root'])/'captures/01.png',p)
print(json.dumps({'files':['composed.png']}))
''')
        recipe = copy.deepcopy(self.recipe)
        recipe['composer'] = {'argv': [sys.executable, '{root}/helpers/composer.py']}
        recipe['outputs'][0]['source'] = 'composed.png'
        with patch.dict('os.environ', {'FASTLANE_PASSWORD': 'not-for-local-tools'}):
            first = self.generate(recipe)
        self.assertEqual(first, self.generate(recipe))
        record = self.snapshots.validate_snapshot(first)['record']
        self.assertIn('helpers/composer.py', record['inputs'])
        self.assertIn('composed.png', record['composed_inputs'])
        helper.write_text(helper.read_text() + '# changed composition recipe\n')
        self.assertNotEqual(first, self.generate(recipe))

    def test_jpeg_outputs_match_the_declared_extension_and_are_reproducible(self):
        recipe = copy.deepcopy(self.recipe)
        recipe['outputs'][0]['file'] = 'images/en-US/01.jpg'
        first = self.generate(recipe)
        self.assertEqual(first, self.generate(recipe))
        self.assertEqual((first / 'images/en-US/01.jpg').read_bytes()[:3], b'\xff\xd8\xff')

    def test_transparent_pixels_need_an_explicit_background(self):
        (self.root / 'captures/01.png').write_bytes(png(alpha=True, opacity=100))
        with self.assertRaisesRegex(ValueError, 'background|transparent'):
            self.generate()
        recipe = copy.deepcopy(self.recipe)
        recipe['outputs'][0]['background'] = '#ffffff'
        self.generate(recipe)

    def test_native_capture_status_requires_capture_time_build_evidence(self):
        recipe = copy.deepcopy(self.recipe)
        recipe['provenance'] = {'status': 'verified-native-capture'}
        with self.assertRaisesRegex(ValueError, 'capture|evidence'):
            self.generate(recipe)

    def test_hidden_format_alpha_and_unknown_slots_are_rejected(self):
        image = self.root / 'captures/01.png'
        image.write_bytes(png())
        for name, slot, message in [('.hidden.png', 'APP_IPHONE_65', 'hidden'),
                                    ('wrong.jpg', 'APP_IPHONE_65', 'format'),
                                    ('valid.png', 'UNKNOWN_NEW_SLOT', 'slot')]:
            path = image.with_name(name)
            path.write_bytes(image.read_bytes())
            entry = {'file': path.relative_to(self.root).as_posix(), 'locale': 'en-US', 'slot': slot}
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, message):
                self.catalog.validate_images(self.root, [entry], 'apple')
        with self.assertRaisesRegex(ValueError, 'alpha'):
            image.write_bytes(png(alpha=True))
            self.catalog.validate_images(self.root, [{'file': 'captures/01.png', 'locale': 'en-US', 'slot': 'APP_IPHONE_65'}], 'apple')

    def test_disguised_vector_is_rejected_before_any_decoder_delegate(self):
        (self.root / 'captures/01.png').write_text('<svg>untrusted vector</svg>')
        with patch('subprocess.run', side_effect=AssertionError('decoder must not run')):
            with self.assertRaisesRegex(ValueError, 'format|signature'):
                self.catalog.validate_images(self.root, [{'file': 'captures/01.png', 'locale': 'en-US', 'slot': 'APP_IPHONE_65'}], 'apple')

    def test_google_phone_rules_allow_composed_artwork_but_reject_raw_ratio(self):
        entry = {'file': 'captures/01.png', 'locale': 'ko-KR', 'slot': 'phoneScreenshots'}
        (self.root / entry['file']).write_bytes(png(810, 1440))
        self.catalog.validate_images(self.root, [entry], 'google')
        (self.root / entry['file']).write_bytes(png(1080, 2400))
        with self.assertRaisesRegex(ValueError, 'ratio|dimension'):
            self.catalog.validate_images(self.root, [entry], 'google')

    def test_google_icon_allows_rgba_but_screenshots_do_not(self):
        (self.root / 'captures/01.png').write_bytes(png(512, 512, alpha=True))
        entry = {'file': 'captures/01.png', 'locale': 'en-US', 'slot': 'icon'}
        self.catalog.validate_images(self.root, [entry], 'google')
        with self.assertRaisesRegex(ValueError, 'alpha'):
            self.catalog.validate_images(self.root, [dict(entry, slot='phoneScreenshots')], 'google')

    def test_catalog_reports_current_submission_required_classes_separately(self):
        report = self.catalog.submission_readiness('apple', ['APP_IPHONE_65'], supports_ipad=True)
        self.assertFalse(report['ready'])
        self.assertIn('APP_IPHONE_61', report['missing'])
        self.assertIn('APP_IPAD_PRO_3GEN_129', report['missing'])

    def test_apple_keyword_limit_counts_utf8_bytes_and_google_short_text_limit(self):
        with self.assertRaisesRegex(ValueError, 'keywords'):
            self.catalog.validate_fields({'ko': {'keywords': '가' * 34}}, 'apple')
        with self.assertRaisesRegex(ValueError, 'short_description'):
            self.catalog.validate_fields({'en-US': {'short_description': 'x' * 81}}, 'google')
        self.catalog.validate_fields({'ko': {'keywords': '가' * 33}}, 'apple')


class ImagePlanTests(unittest.TestCase):
    def test_selected_asset_manifest_is_bound_and_cache_tampering_blocks(self):
        planning = module(self, 'planning')
        root, profile = fixture(self)
        (root / 'captures').mkdir()
        (root / 'captures/01.png').write_bytes(png())
        generation = module(self, 'generation')
        recipe = {'schema_version': 1, 'target': profile['targets']['production'], 'inputs': ['captures'],
                  'outputs': [{'source': 'captures/01.png', 'file': 'images/01.png', 'locale': 'en-US', 'slot': 'APP_IPHONE_65'}],
                  'toolchain': generation.toolchain(), 'provenance': {'status': 'unverified-import'}}
        snapshot = generation.generate(root, recipe, root / 'asset-history')
        image = snapshot / 'images/01.png'
        listing = json.loads((root / 'metadata/listing.json').read_text())
        listing['images'] = {'en-US': {'APP_IPHONE_65': [{'file': image.relative_to(root).as_posix(), 'sha256': hashlib.sha256(image.read_bytes()).hexdigest()}]}}
        write_json(root / 'metadata/listing.json', listing)
        target = profile['targets']['production']
        target['assets'] = {'manifest': (snapshot / 'manifest.json').relative_to(root).as_posix()}
        target['replacement'] = {'locales': ['en-US'], 'slots': ['APP_IPHONE_65'], 'allow_delete': False}
        write_json(root / 'store-upload.json', profile)
        plan = planning.make_plan(root, 'store-upload.json', 'production', 'images')
        self.assertIn(target['assets']['manifest'], plan['payload']['inputs'])
        manifest = json.loads((snapshot / 'manifest.json').read_text())
        manifest['record']['provenance'] = {'status': 'verified-native-capture'}
        write_json(snapshot / 'manifest.json', manifest)
        with self.assertRaisesRegex(ValueError, 'snapshot|manifest|address'):
            planning.verify_plan(root, plan)

    def test_listing_image_bytes_and_inventory_are_bound_before_transfer(self):
        planning = module(self, 'planning')
        root, profile = fixture(self)
        (root / 'images').mkdir()
        image = root / 'images/01.png'
        image.write_bytes(png())
        listing = json.loads((root / 'metadata/listing.json').read_text())
        listing['images'] = {'en-US': {'APP_IPHONE_65': [{'file': 'images/01.png', 'sha256': hashlib.sha256(image.read_bytes()).hexdigest()}]}}
        write_json(root / 'metadata/listing.json', listing)
        profile['targets']['production']['replacement'] = {'locales': ['en-US'], 'slots': ['APP_IPHONE_65'], 'allow_delete': False}
        write_json(root / 'store-upload.json', profile)
        plan = planning.make_plan(root, 'store-upload.json', 'production', 'images')
        self.assertIn('images/01.png', plan['payload']['inputs'])
        image.write_bytes(png(1284, 2778))
        with self.assertRaisesRegex(ValueError, 'hash|changed|differs'):
            planning.verify_plan(root, plan)


if __name__ == '__main__':
    unittest.main()
