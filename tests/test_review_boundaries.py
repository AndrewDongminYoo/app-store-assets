"""Provider protocol and target regressions with synthetic, offline inputs."""
import json
import os
import shutil
import subprocess
import unittest

from pipeline_support import ROOT, fixture, module, write_json


class ReviewBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.root, self.profile = fixture(self)

    def test_unicode_protocol_uses_utf8_on_supported_ruby_interpreters(self):
        rubies = {shutil.which('ruby')}
        if os.environ.get('APP_STORE_ASSETS_READER_RUBY'):
            rubies.add(os.environ['APP_STORE_ASSETS_READER_RUBY'])
        request = {'target': '미래 ✨', 'notes': '새 기능', 'path': '이미지/01.png'}
        for ruby in filter(None, rubies):
            with self.subTest(ruby=ruby):
                result = module(self, 'commands').run_command(
                    [ruby, '-rjson', '-e', 'puts JSON.generate(JSON.parse($stdin.read))'],
                    request, self.root, self.root / 'protocol-home')
                self.assertEqual(result, request)

    def test_download_stages_declared_gemfile_and_lock_outside_provider_inputs(self):
        from app_store_assets import cli
        target = self.profile['targets']['production']
        target['provider']['gemfile'] = 'sdk/Gemfile'
        (self.root / 'sdk').mkdir()
        (self.root / 'sdk/Gemfile').write_text('synthetic locked SDK')
        (self.root / 'sdk/Gemfile.lock').write_text('synthetic lock bytes')
        (self.root / 'helpers/provider.py').write_text('''import json, os, pathlib, sys
request = json.load(sys.stdin)
assert request['action'] == 'download'
gemfile = pathlib.Path(os.environ['BUNDLE_GEMFILE'])
assert gemfile.read_text() == 'synthetic locked SDK'
assert pathlib.Path(str(gemfile) + '.lock').read_text() == 'synthetic lock bytes'
print(json.dumps({'record': {'target': request['target'], 'fields': {}, 'images': {}}}))
''')
        write_json(self.root / 'store-upload.json', self.profile)
        import io
        from contextlib import redirect_stdout, redirect_stderr
        output, errors = io.StringIO(), io.StringIO()
        with redirect_stdout(output), redirect_stderr(errors):
            status = cli.main(['download', '--root', str(self.root), '--target', 'production', '--allow-effects'])
        self.assertEqual(status, 0, errors.getvalue())
        self.assertTrue((self.root / json.loads(output.getvalue())['snapshot']).is_dir())

    def test_metadata_requires_complete_account_and_track_identity(self):
        for store, key, bad in [('apple', 'account_id', 'other-issuer'),
                                ('google', 'account_id', 'other-service-account'),
                                ('google', 'track', 'production')]:
            with self.subTest(store=store, key=key):
                root, profile = fixture(self, store=store)
                target = profile['targets']['production']
                target['account_id'] = 'approved-account'
                identity = module(self, 'profiles').target_identity(target)
                listing = json.loads((root / 'metadata/listing.json').read_text())
                listing['target'] = dict(identity, **{key: bad})
                write_json(root / 'metadata/listing.json', listing)
                remote = json.loads((root / 'remote.json').read_text())
                remote['target'] = identity
                write_json(root / 'remote.json', remote)
                write_json(root / 'store-upload.json', profile)
                with self.assertRaisesRegex(ValueError, 'metadata.*target'):
                    module(self, 'planning').make_plan(root, 'store-upload.json', 'production', 'metadata')

    def test_listing_operations_without_declared_listing_fail_before_plan(self):
        del self.profile['targets']['production']['metadata']
        write_json(self.root / 'store-upload.json', self.profile)
        for operation in ('metadata', 'images'):
            with self.subTest(operation=operation), self.assertRaisesRegex(ValueError, 'listing|metadata'):
                module(self, 'planning').make_plan(self.root, 'store-upload.json', 'production', operation)
        self.assertFalse((self.root / 'build').exists())

    def test_pinned_fastlane_app_info_exposes_state_and_selects_editable_info(self):
        sdk = os.environ.get('APP_STORE_ASSETS_FASTLANE_SOURCE')
        if not sdk:
            self.skipTest('set APP_STORE_ASSETS_FASTLANE_SOURCE for the pinned AppInfo model')
        source = r'''
require 'json'; require 'ostruct'; require 'tmpdir'; require 'net/http'
Net::HTTP.define_singleton_method(:start) { |*a, **kw| raise 'network forbidden' }
$LOAD_PATH.unshift(File.join(ARGV[1], 'fastlane/lib'))
require 'fastlane/version'
raise 'unexpected SDK version' unless Fastlane::VERSION == '2.240.1'
require File.join(ARGV[1], 'spaceship/lib/spaceship/connect_api/models/app_info')
require ARGV[0]
info = Spaceship::ConnectAPI::AppInfo.new('editable-info', {'state'=>'PREPARE_FOR_SUBMISSION'})
raise 'incorrect state accessor' unless info.state == 'PREPARE_FOR_SUBMISSION'
raise 'invented app_info_state accessor' if info.respond_to?(:app_info_state)
info.define_singleton_method(:get_app_info_localizations) do
  [OpenStruct.new(locale:'ko', name:'미래', subtitle:'새 소식', privacy_policy_url:'https://example.invalid/privacy')]
end
closed = Spaceship::ConnectAPI::AppInfo.new('closed-info', {'state'=>'READY_FOR_DISTRIBUTION'})
Spaceship::ConnectAPI.define_singleton_method(:get_app_infos) { |**kw| OpenStruct.new(to_models:[closed,info]) }
Spaceship::ConnectAPI.singleton_class.attr_accessor :token
module Spaceship
  class ConnectAPI
    class Token
      def self.from_json_file(*); :synthetic_token; end
    end
    class App
      def self.find(*)
        app = OpenStruct.new(id:'synthetic-app', bundle_id:'com.example.fixture')
        app.define_singleton_method(:get_app_store_versions) { |**kw| [] }
        app.define_singleton_method(:get_builds) { |**kw| [] }
        app
      end
    end
  end
end
$LOADED_FEATURES << 'spaceship.rb'
Dir.mktmpdir do |root|
  auth = File.join(root, 'synthetic-auth.json')
  File.write(auth, JSON.generate(issuer_id:'synthetic-issuer'))
  target = {'store'=>'apple','platform'=>'ios','app_id'=>'com.example.fixture', 'account_id'=>'synthetic-issuer',
    'version'=>{'name'=>'1.0','build'=>'9'}}
  result = StoreProvider.run({'authorized'=>true,'mode'=>'live','auth_file'=>auth,'target'=>target,'action'=>'snapshot'})
  raise 'editable AppInfo not selected' unless result['app_info_id']=='editable-info'
  raise 'localized AppInfo lost' unless result.dig('fields','ko','name')=='미래'
end
'''
        result = subprocess.run([os.environ.get('APP_STORE_ASSETS_READER_RUBY', 'ruby'), '-e', source,
                                 str(ROOT / 'lib/store_provider.rb'), sdk], capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
