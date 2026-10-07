"""Run repository Ruby adapters with synthetic SDK models and no auth/network."""
import subprocess
import os
import unittest
from pathlib import Path

from pipeline_support import ROOT

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
  def upload_bundle(path); @events << ['upload']; OpenStruct.new(version_code:9); end
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
    'replacement'=>{'locales'=>['en-US'],'slots'=>['phoneScreenshots'],'allow_delete'=>false}}
  result=provider.upload({'payload'=>gp},root)
  raise 'upload IDs missing for transformed readback' unless result.dig('image_ids','en-US','phoneScreenshots')==['uploaded-image']
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

    def test_google_revision_is_rechecked_inside_write_edit(self):
        self.run_case('drift')

    def test_google_upload_ids_bind_transformed_image_readback(self):
        self.run_case('image_ids')

    def test_actual_supply_sdk_image_fields(self):
        root = os.environ.get('APP_STORE_ASSETS_FASTLANE_SOURCE')
        if not root:
            self.skipTest('set APP_STORE_ASSETS_FASTLANE_SOURCE for actual pinned Supply SDK model')
        self.run_case(image_model=str(Path(root) / 'supply/lib/supply/image_listing.rb'))

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
