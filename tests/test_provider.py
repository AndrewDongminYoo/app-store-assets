"""Run repository Ruby adapters with synthetic SDK models and no auth/network."""
import subprocess
import os
import json
import unittest
from pathlib import Path

from pipeline_support import ROOT, fixture, module, write_json

RUBY = r'''
require 'json'
require 'ostruct'
require 'tmpdir'
require ARGV.fetch(0)
if ARGV[1] && !ARGV[1].empty?
  require ARGV[1]
else
  module Supply
    ImageListing=Struct.new(:id,:sha1,:sha256,:url)
  end
end
target={'store'=>'apple','platform'=>'ios','account'=>'personal','app_id'=>'com.example.fixture',
  'flavor'=>'production','stage'=>'production','version'=>{'name'=>'1.0','build'=>'9'}}
class Localization
  attr_reader :locale, :writes
  def initialize; @locale='en-US'; @writes=[]; end
  def description; 'original'; end
  def keywords; ''; end
  def promotional_text; ''; end
  def whats_new; ''; end
  def support_url; ''; end
  def marketing_url; ''; end
  def get_app_screenshot_sets; []; end
  def update(attributes:); @writes << attributes; end
end
class Version
  attr_reader :id,:version_string,:localization
  def initialize(name); @version_string=name; @id='id-'+name; @localization=Localization.new; end
  def app_store_state; 'PREPARE_FOR_SUBMISSION'; end
  def get_app_store_version_localizations; [localization]; end
end
class App
  attr_reader :versions
  def initialize; @versions=[Version.new('1.1'),Version.new('1.0')]; end
  def bundle_id; 'com.example.fixture'; end
  def get_app_store_versions(**); versions; end
  def get_builds(**); []; end
end
app=App.new
adapter=StoreProvider::Apple.new(app)
remote=adapter.snapshot(target)
raise 'highest editable version selected' unless remote['version_id']=='id-1.0'
payload={'target'=>target,'operation'=>'metadata','remote'=>remote,
  'listing'=>{'fields'=>{'en-US'=>{'description'=>'approved text'}},'images'=>{}},'replacement'=>nil}
adapter.upload({'payload'=>payload},Dir.pwd)
raise 'wrong version mutated' unless app.versions[0].localization.writes.empty?
raise 'exact version not updated' unless app.versions[1].localization.writes==[{'description'=>'approved text'}]
payload['remote']=remote.merge('version_id'=>'id-1.1')
begin
  adapter.upload({'payload'=>payload},Dir.pwd)
  raise 'conflicting version ID accepted'
rescue => e
  raise unless e.message.include?('snapshot') || e.message.include?('version')
end

class GoogleClient
  attr_reader :events
  def initialize; @events=[]; end
  def begin_edit(package_name:); @events << ['begin',package_name]; end
  def abort_current_edit; @events << ['abort']; end
  def commit_current_edit!; raise 'read committed edit'; end
  def listings; []; end
  def track_releases(track); []; end
  def aab_version_codes; []; end
  def apks_version_codes; []; end
end
google=GoogleClient.new
gt=target.merge('store'=>'google','platform'=>'android','track'=>'internal')
observed=StoreProvider::Google.new(google).snapshot(gt)
raise 'read-only edit not disclosed' unless observed['effects'].include?('open-read-session')
raise 'read edit not aborted' unless google.events==[['begin','com.example.fixture'],['abort']]
class ImageClient < GoogleClient
  def listings; [OpenStruct.new(language:'en-US',title:'Fixture',short_description:'Short',full_description:'Full',video:'')]; end
  def fetch_images(image_type:,language:)
    image_type=='phoneScreenshots' ? [Supply::ImageListing.new('actual-sdk-id','sha1','a'*64,'https://example.invalid/image')] : []
  end
end
image_snapshot=StoreProvider::Google.new(ImageClient.new).snapshot(gt)
raise 'actual SDK image ID lost' unless image_snapshot['images']['en-US']['phoneScreenshots'][0]['id']=='actual-sdk-id'
omitted=remote.merge('images'=>{'en-US'=>{'APP_IPAD_PRO_129'=>[{'id'=>'ipad'}]}})
image_payload={'target'=>target,'operation'=>'images','remote'=>omitted,
  'listing'=>{'images'=>{'en-US'=>{'APP_IPHONE_65'=>[{'file'=>'image.png'}]}}},
  'replacement'=>{'locales'=>['en-US'],'slots'=>['APP_IPHONE_65'],'allow_delete'=>false}}
begin
  StoreProvider.guard(image_payload,omitted)
  raise 'omitted iPad accepted'
rescue => e
  raise unless e.message.include?('omitted')
end
module ::Google
  module Apis
    module AndroidpublisherV3
      class LocalizedText < OpenStruct; end
      class TrackRelease < OpenStruct; end
      class Track < OpenStruct; end
    end
  end
end
$LOADED_FEATURES << 'google/apis/androidpublisher_v3.rb'
class WriteClient < GoogleClient
  attr_reader :written_track
  # Supply::Client#upload_bundle returns the integer versionCode, not a Bundle.
  def upload_bundle(path); @events << ['upload']; 9; end
  def update_track(name, track); @written_track=[name,track]; end
  def validate_current_edit!; @events << ['validate']; end
  def commit_current_edit!; @events << ['commit']; end
end
Dir.mktmpdir do |root|
  File.binwrite(File.join(root,'app.aab'),'approved')
  client=WriteClient.new
  provider=StoreProvider::Google.new(client)
  gp={'target'=>gt,'operation'=>'binary','remote'=>provider.snapshot(gt),'release_status'=>'draft',
    'release_notes'=>{'en-US'=>'notes'},'artifact'=>{'path'=>'app.aab'},
    'build'=>{'sha256'=>Digest::SHA256.hexdigest('approved')}}
  provider.upload({'payload'=>gp},root)
  raise 'track/status mismatch' unless client.written_track[0]=='internal' && client.written_track[1].releases.last.status=='draft'
  raise 'notes omitted' unless client.written_track[1].releases.last.release_notes.first.text=='notes'
  raise 'write not explicitly committed' unless client.events.last==['commit']
end
class DriftClient < WriteClient
  def track_releases(track)
    events.count { |e| e[0]=='begin' } >= 3 ? [OpenStruct.new(name:'concurrent',status:'completed',version_codes:[8],release_notes:[])] : []
  end
end
if ARGV[2]=='drift'
Dir.mktmpdir do |root|
  File.binwrite(File.join(root,'app.aab'),'approved')
  client=DriftClient.new
  provider=StoreProvider::Google.new(client)
  gp={'target'=>gt,'operation'=>'binary','remote'=>provider.snapshot(gt),'release_status'=>'draft',
    'release_notes'=>{},'artifact'=>{'path'=>'app.aab'},'build'=>{'sha256'=>Digest::SHA256.hexdigest('approved')}}
  begin
    provider.upload({'payload'=>gp},root)
    raise 'write-edit revision drift accepted'
  rescue => e
    raise unless e.message.include?('snapshot')
  end
  raise 'upload before write-edit preflight' if client.events.any? { |e| e[0]=='upload' }
end
end
class ImageWriteClient < ImageClient
  def clear_screenshots(**); end
  def upload_image(**); OpenStruct.new(image: OpenStruct.new(id:'uploaded-image')); end
  def validate_current_edit!; end
  def commit_current_edit!; end
end
if ARGV[2]=='image_ids'
Dir.mktmpdir do |root|
  File.binwrite(File.join(root,'image.png'),'approved')
  provider=StoreProvider::Google.new(ImageWriteClient.new)
  gp={'target'=>gt,'operation'=>'images','remote'=>provider.snapshot(gt),
    'listing'=>{'images'=>{'en-US'=>{'phoneScreenshots'=>[{'file'=>'image.png','sha256'=>Digest::SHA256.hexdigest('approved')}]}}},
    'replacement'=>{'locales'=>['en-US'],'slots'=>['phoneScreenshots'],'allow_delete'=>true}}
  result=provider.upload({'payload'=>gp},root)
  raise 'upload IDs missing for transformed readback' unless result.dig('image_ids','en-US','phoneScreenshots')==['uploaded-image']
end
end
if ARGV[2]=='delete_policy'
  observed=remote.merge('images'=>{'en-US'=>{'APP_IPHONE_65'=>[{'id'=>'existing'}]}})
  gp={'target'=>target,'operation'=>'images','remote'=>observed,
    'listing'=>{'images'=>{'en-US'=>{'APP_IPHONE_65'=>[{'file'=>'synthetic.png'}]}}},
    'replacement'=>{'locales'=>['en-US'],'slots'=>['APP_IPHONE_65'],'allow_delete'=>false}}
  begin
    StoreProvider.guard(gp,observed)
    raise 'existing screenshot deletion policy ignored'
  rescue => e
    raise unless e.message.include?('requires explicit')
  end
end
if ARGV[2]=='apple_platform'
  class BuildApp < App
    attr_accessor :builds
    def get_builds(**); builds; end
  end
  app=BuildApp.new
  mac=OpenStruct.new(version:'9',processing_state:'VALID',pre_release_version:OpenStruct.new(version:'1.0',platform:'MAC_OS'))
  ios=OpenStruct.new(version:'9',processing_state:'VALID',pre_release_version:OpenStruct.new(version:'1.0',platform:'IOS'))
  app.builds=[mac]
  provider=StoreProvider::Apple.new(app)
  raise 'macOS build recognized as iOS' unless provider.snapshot(target)['binary'].nil?
  app.builds=[mac,ios]
  raise 'actual iOS build platform missing' unless provider.snapshot(target).dig('binary','platform')=='ios'
end
if ARGV[2]=='download_annotations'
  module StoreProvider
    def self.download_image(url,destination)
      path=destination+'.png'; FileUtils.mkdir_p(File.dirname(path)); File.binwrite(path,'synthetic-image'); path
    end
  end
  image=OpenStruct.new(id:'image-1',asset_delivery_state:{'state'=>'COMPLETE'},
    image_asset:{'templateUrl'=>'https://example.invalid/{w}x{h}.{f}','width'=>1242,'height'=>2688})
  set=OpenStruct.new(screenshot_display_type:'APP_IPHONE_65',app_screenshots:[image])
  app=App.new
  app.versions.last.localization.define_singleton_method(:get_app_screenshot_sets) { [set] }
  apple=StoreProvider::Apple.new(app)
  google=StoreProvider::Google.new(ImageClient.new)
  Dir.mktmpdir do |root|
    puts JSON.generate(downloads:[{'record'=>apple.download(target,root)['record'],'observed'=>apple.snapshot(target)},
      {'record'=>google.download(gt,root)['record'],'observed'=>google.snapshot(gt)}])
  end
end
puts JSON.generate(exact_version: true, conflicting_id_blocked: true, google_read_never_commits: true)
'''


class ProviderTests(unittest.TestCase):
    def run_case(self, case='base', image_model=''):
        result = subprocess.run(['ruby', '-e', RUBY, str(ROOT / 'lib/store_provider.rb'), image_model, case],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result

    def test_exact_apple_metadata_version_and_google_read_session_under_stubs(self):
        result = self.run_case()
        self.assertIn('"exact_version":true', result.stdout)
        self.assertIn('"google_read_never_commits":true', result.stdout)

    def test_all_app_info_locales_are_checked_before_any_metadata_write(self):
        source = r'''
require 'json'; require ARGV.fetch(0)
writes=[]
locales=%w(en-US ko-KR).map do |name|
  item=Object.new
  item.define_singleton_method(:locale) { name }
  item.define_singleton_method(:update) { |attributes:| writes << [name,attributes] }
  item
end
version=Object.new
version.define_singleton_method(:id) { 'exact-version' }
version.define_singleton_method(:get_app_store_version_localizations) { locales }
info_locales=[locales.first]
info=Object.new
info.define_singleton_method(:id) { 'exact-info' }
info.define_singleton_method(:get_app_info_localizations) { info_locales }
target={'app_id'=>'com.example.synthetic'}
remote={'target'=>target,'version_id'=>'exact-version','app_info_id'=>'exact-info',
  'editable'=>true,'review_active'=>false}
provider=StoreProvider::Apple.new(Object.new,app_info:info)
provider.define_singleton_method(:snapshot) { |_| remote }
provider.define_singleton_method(:version) { |_| version }
[
  {'ko-KR'=>{'description'=>'reviewed description','name'=>'reviewed name'}},
  {'en-US'=>{'description'=>'reviewed description'},'ko-KR'=>{'name'=>'reviewed name'}}
].each do |fields|
  payload={'operation'=>'metadata','target'=>target,'remote'=>remote,'listing'=>{'fields'=>fields}}
  begin
    provider.upload({'payload'=>payload},'/unused-synthetic-path')
    raise 'missing AppInfo locale accepted'
  rescue => error
    raise unless error.message=='missing exact app-info localization'
    raise 'metadata changed before all AppInfo locales were validated' unless writes.empty?
  end
end
info_locales << locales.last
payload={'operation'=>'metadata','target'=>target,'remote'=>remote,
  'listing'=>{'fields'=>{'ko-KR'=>{'description'=>'reviewed description','name'=>'reviewed name'}}}}
raise 'acceptance missing' unless provider.upload({'payload'=>payload},'/unused-synthetic-path')['accepted']
raise 'valid mixed metadata not written exactly' unless writes==[
  ['ko-KR',{'description'=>'reviewed description'}],['ko-KR',{'name'=>'reviewed name'}]]
'''
        result = subprocess.run(['ruby', '-e', source, str(ROOT / 'lib/store_provider.rb')],
                                capture_output=True, text=True, timeout=30, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_google_revision_is_rechecked_inside_write_edit(self):
        self.run_case('drift')

    def test_google_upload_ids_bind_transformed_image_readback(self):
        self.run_case('image_ids')

    def test_deleting_existing_images_requires_explicit_policy(self):
        self.run_case('delete_policy')

    def test_apple_builds_are_filtered_by_actual_platform(self):
        self.run_case('apple_platform')

    def test_nonempty_native_downloads_plan_and_preflight_without_losing_file_binding(self):
        result = self.run_case('download_annotations')
        records = next(json.loads(line)['downloads'] for line in result.stdout.splitlines() if 'downloads' in line)
        for value in records:
            with self.subTest(store=value['record']['target']['store']):
                root, profile = fixture(self, store=value['record']['target']['store'])
                target = profile['targets']['production']
                if target['store'] == 'google':
                    target['track'] = 'internal'
                    listing = json.loads((root / 'metadata/listing.json').read_text())
                    listing['target'] = module(self, 'profiles').target_identity(target)
                    write_json(root / 'metadata/listing.json', listing)
                files = {item['file']: b'synthetic-image' for groups in value['record']['images'].values()
                         for images in groups.values() for item in images}
                snapshot = module(self, 'snapshots').publish_snapshot(root / 'downloads', value['record'], files)
                target['remote'] = (snapshot / 'manifest.json').relative_to(root).as_posix()
                write_json(root / 'store-upload.json', profile)
                plan = module(self, 'planning').make_plan(root, 'store-upload.json', 'production', 'metadata')
                observed = module(self, 'metadata').normalize_remote(value['observed'], plan['payload']['target'])
                module(self, 'execution').preflight(plan['payload'], observed)
                planned_image = next(item for groups in plan['payload']['remote']['images'].values()
                                     for images in groups.values() for item in images)
                self.assertNotIn('file', planned_image)
                changed = json.loads(json.dumps(observed))
                changed_image = next(item for groups in changed['images'].values() for images in groups.values() for item in images)
                changed_image['id'] = 'concurrent-image'
                with self.assertRaisesRegex(ValueError, 'snapshot|revision'):
                    module(self, 'execution').preflight(plan['payload'], changed)
                (snapshot / next(iter(files))).write_bytes(b'changed local download')
                with self.assertRaisesRegex(ValueError, 'hash|inventory|manifest'):
                    module(self, 'planning').verify_plan(root, plan)

    def test_apple_download_rejects_complete_second_inventory_drift_before_any_download(self):
        source = r'''require "json"; require "ostruct"; require "tmpdir"; require ARGV.fetch(0)
        target = {"app_id"=>"com.example.fixture"}
        original = {"version_id"=>"version-1", "images"=>{"en-US"=>{"APP_IPHONE_65"=>[{"id"=>"a"},{"id"=>"b"}]}}}
        module StoreProvider
          def self.download_image(*); raise "download called before complete identity guard"; end
        end
        [["b","a"], ["a"], ["a","b","c"], ["a","changed"]].each do |ids|
          images = ids.map { |id| OpenStruct.new(id:id, image_asset:{"templateUrl"=>"https://example.invalid/{w}x{h}.{f}", "width"=>1,"height"=>1}) }
          set = OpenStruct.new(screenshot_display_type:"APP_IPHONE_65", app_screenshots:images)
          locale = Object.new
          locale.define_singleton_method(:locale) { "en-US" }
          locale.define_singleton_method(:get_app_screenshot_sets) { [set] }
          version = Object.new
          version.define_singleton_method(:id) { "version-1" }
          version.define_singleton_method(:get_app_store_version_localizations) { [locale] }
          provider = StoreProvider::Apple.new(Object.new)
          provider.define_singleton_method(:snapshot) { |_| Marshal.load(Marshal.dump(original)) }
          provider.define_singleton_method(:version) { |_| version }
          begin
            Dir.mktmpdir { |dir| provider.download(target,dir) }
            raise "changed inventory accepted"
          rescue => error
            raise unless error.message.include?("screenshot inventory changed")
          end
        end
        puts JSON.generate(blocked:true)
        '''
        result = subprocess.run(['ruby', '-e', source, str(ROOT / 'lib/store_provider.rb')],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_actual_supply_sdk_image_fields(self):
        root = os.environ.get('APP_STORE_ASSETS_FASTLANE_SOURCE')
        if not root:
            self.skipTest('set APP_STORE_ASSETS_FASTLANE_SOURCE for actual pinned Supply SDK model')
        self.run_case(image_model=str(Path(root) / 'supply/lib/supply/image_listing.rb'))

    def test_actual_supply_upload_bundle_scalar_is_accepted(self):
        root = os.environ.get('APP_STORE_ASSETS_FASTLANE_SOURCE')
        if not root:
            self.skipTest('set APP_STORE_ASSETS_FASTLANE_SOURCE for actual pinned Supply client')
        source = r'''
require 'json'; require 'ostruct'; require 'tmpdir'; require 'net/http'
Net::HTTP.define_singleton_method(:start) { |*args, **kwargs| raise 'network forbidden' }
$LOAD_PATH.unshift(*Dir.glob(File.join(ARGV[1], '*/lib')))
require 'supply/client'
module Supply; class << self; attr_accessor :config; end; end
Supply.config={ack_bundle_installation_warning:false}
require ARGV[0]
class NativeReturnClient < Supply::Client
  attr_reader :events
  def initialize; @events=[]; end
  def begin_edit(package_name:); @events << 'begin'; self.current_edit=OpenStruct.new(id:'fixture'); self.current_package_name=package_name; end
  def abort_current_edit; @events << 'abort'; self.current_edit=nil; end
  def listings; []; end
  def track_releases(track); []; end
  def aab_version_codes; []; end
  def apks_version_codes; []; end
  def validate_current_edit!; @events << 'validate'; end
  def commit_current_edit!; @events << 'commit'; end
  def update_track(*); @events << 'update-track'; end
end
client=NativeReturnClient.new
transport=Object.new
transport.define_singleton_method(:upload_edit_bundle) { |*args,**kwargs| Google::Apis::AndroidpublisherV3::Bundle.new(version_code:9) }
client.client=transport
target={'store'=>'google','platform'=>'android','account'=>'fixture','app_id'=>'com.example.fixture',
  'flavor'=>'production','stage'=>'production','track'=>'internal','version'=>{'name'=>'1.0','build'=>'9'}}
Dir.mktmpdir do |folder|
  File.binwrite(File.join(folder,'app.aab'),'synthetic-binary')
  provider=StoreProvider::Google.new(client)
  payload={'target'=>target,'operation'=>'binary','remote'=>provider.snapshot(target),'release_status'=>'draft',
    'release_notes'=>{},'artifact'=>{'path'=>'app.aab'},'build'=>{'sha256'=>Digest::SHA256.hexdigest('synthetic-binary')}}
  raise 'acceptance missing' unless provider.upload({'payload'=>payload},folder)['accepted']
  raise 'scalar result did not reach track/commit' unless client.events.last(3)==['update-track','validate','commit']
end
'''
        sdk = Path(root)
        env = dict(os.environ, GEM_HOME=str(sdk.parent.parent), GEM_PATH=str(sdk.parent.parent))
        result = subprocess.run([os.environ.get('APP_STORE_ASSETS_READER_RUBY', 'ruby'), '-e', source,
                                 str(ROOT / 'lib/store_provider.rb'), str(sdk)], env=env,
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_cli_adapter_missing_authority_stops_before_sdk_authentication(self):
        result = subprocess.run(['ruby', str(ROOT / 'lib/store_provider.rb')], input='{"action":"snapshot"}',
                                capture_output=True, text=True, timeout=30)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('authorization', result.stderr.lower())
        self.assertNotIn('login', result.stdout.lower())

    def test_unsupported_native_store_blocks_before_protected_auth_read(self):
        source = '''require ARGV[0]
begin
  StoreProvider.run({'authorized'=>true,'mode'=>'live','auth_file'=>'/missing-synthetic-auth',
    'target'=>{'store'=>'toss','account_id'=>'fixture'}})
rescue => e
  abort e.message unless e.message.include?('native provider')
end
'''
        result = subprocess.run(['ruby', '-e', source, str(ROOT / 'lib/store_provider.rb')], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
