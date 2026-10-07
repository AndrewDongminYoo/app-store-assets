"""Host contracts for adapters and offline store prerequisites."""
import json
import sys
import unittest
from unittest.mock import patch

from pipeline_support import fixture, module, write_json


class AdapterBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.root, self.profile = fixture(self)

    def test_provider_absolute_script_is_rejected_before_plan_or_effects(self):
        target = self.profile['targets']['production']
        target['provider']['argv'][1] = str(self.root / 'helpers/provider.py')
        write_json(self.root / 'store-upload.json', self.profile)
        with patch('subprocess.run', side_effect=AssertionError('adapter must not run')):
            with self.assertRaisesRegex(ValueError, 'staged|adapter.*path'):
                module(self, 'profiles').load_profile(self.root, 'store-upload.json', 'production')
        self.assertFalse((self.root / 'build/store-assets').exists())

    def test_expansion_rejects_absolute_options_and_parent_escapes(self):
        commands = module(self, 'commands')
        for arg in ('/original/provider.py', '--script=/original/provider.py', '-r/original/provider.rb',
                    '-I/original/modules',
                    '../provider.py', '{root}/../provider.py', '{runtime}/../provider.rb'):
            with self.subTest(arg=arg):
                with self.assertRaisesRegex(ValueError, 'staged|adapter.*path'):
                    commands.expand_argv([sys.executable, arg], self.root, self.root / 'runtime')

    def test_staged_script_runs_reviewed_bytes_after_original_changes(self):
        commands = module(self, 'commands')
        original = self.root / 'helpers/provider.py'
        original.write_text('import json; print(json.dumps({"source":"reviewed"}))\n')
        staged = self.root / 'staged'
        (staged / 'helpers').mkdir(parents=True)
        (staged / 'helpers/provider.py').write_bytes(original.read_bytes())
        original.write_text('raise AssertionError("mutable original executed")\n')
        argv = commands.expand_argv([sys.executable, '{root}/helpers/provider.py'], staged)
        self.assertEqual(commands.run_command(argv, {}, staged, self.root / 'private-home'),
                         {'source': 'reviewed'})

    def test_google_rollout_statuses_fail_before_plan(self):
        root, profile = fixture(self, store='google')
        for status in ('inProgress', 'halted'):
            with self.subTest(status=status):
                profile['targets']['production']['release_status'] = status
                write_json(root / 'store-upload.json', profile)
                with self.assertRaisesRegex(ValueError, 'status|rollout'):
                    module(self, 'profiles').load_profile(root, 'store-upload.json', 'production')
        self.assertFalse((root / 'build/store-assets').exists())

    def test_google_title_description_limits_and_alias_fail_during_planning(self):
        root, profile = fixture(self, store='google')
        path = root / 'metadata/listing.json'
        listing = json.loads(path.read_text())
        planning = module(self, 'planning')
        for field, limit in (('title', 30), ('full_description', 4000), ('description', 4000)):
            for length in (limit - 1, limit, limit + 1):
                with self.subTest(field=field, length=length):
                    listing['fields'] = {'ko-KR': {field: '한' * length}}
                    write_json(path, listing)
                    if length > limit:
                        with self.assertRaisesRegex(ValueError, 'limit'):
                            planning.make_plan(root, 'store-upload.json', 'production', 'metadata')
                    else:
                        planning.make_plan(root, 'store-upload.json', 'production', 'metadata')
        self.assertFalse((root / 'build/store-assets').exists())


if __name__ == '__main__':
    unittest.main()
