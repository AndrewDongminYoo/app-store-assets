# A fake Spaceship::ConnectAPI for the snapshot export tests.
# It serves the scenario in FAKE_ASC_SCENARIO and writes every call to FAKE_ASC_LOG.
# Read methods mirror the fastlane 2.240.1 signatures; every write method logs and raises.
require "json"
require "logger"
require "socket"

TCPSocket.define_singleton_method(:new) { |*| raise "network forbidden in fake" }
Socket.define_singleton_method(:tcp) { |*, **| raise "network forbidden in fake" }

# Stands for a filesystem that does not support hard links.
if (link_error = JSON.parse(File.read(ENV.fetch("FAKE_ASC_SCENARIO")))["link_error"])
  File.singleton_class.prepend(Module.new { define_method(:link) { |*| raise Errno.const_get(link_error) } })
end

module FakeASC
  SCENARIO = JSON.parse(File.read(ENV.fetch("FAKE_ASC_SCENARIO")))
  CALLS = []
  # Like Spaceship::Client#logger under VERBOSE: the logger holds the STDOUT object, not $stdout.
  LOGGER = ENV["VERBOSE"] ? Logger.new(STDOUT) : nil
  at_exit { File.write(ENV.fetch("FAKE_ASC_LOG"), JSON.generate(CALLS)) }

  def self.call(name, **arguments)
    CALLS << { "call" => name, "arguments" => arguments.transform_keys(&:to_s) }
    LOGGER&.info(">> GET #{name}")
    puts "fake provider output from #{name}" if SCENARIO["print"]
    if SCENARIO["create_output"] && name == SCENARIO["create_output"]["during"]
      File.write(SCENARIO["create_output"]["path"], SCENARIO["create_output"]["content"])
    end
    # Stands for an output directory that is moved away and replaced by a symbolic link.
    if (swap = SCENARIO["swap_directory"]) && name == swap["during"]
      File.rename(swap["path"], swap["moved_to"])
      File.symlink(swap["replacement"], swap["path"])
    end
    # Stands for a provider call that keeps retrying an HTTP 429 response.
    sleep(SCENARIO["hang"]["seconds"]) if SCENARIO["hang"] && name == SCENARIO["hang"]["call"]
  end

  def self.write(name)
    CALLS << { "call" => name, "arguments" => {} }
    raise "write forbidden in fake: #{name}"
  end

  class Model
    def initialize(data)
      @data = data
    end

    def id
      @data["id"]
    end

    def self.reads(*names)
      names.each { |name| define_method(name) { @data[name.to_s] } }
    end

    def self.writes(*names)
      names.each { |name| define_method(name) { |*, **| FakeASC.write("#{self.class.name.split('::').last}##{name}") } }
    end
  end
end

module Spaceship
  module ConnectAPI
    class App < FakeASC::Model
      reads :bundle_id
      writes :update, :create_review_submission, :ensure_version!, :reject_version_if_possible!

      def self.find(bundle_id, client: nil)
        FakeASC.call("App.find", bundle_id: bundle_id)
        app = FakeASC::SCENARIO["app"]
        app && app["bundle_id"] == bundle_id ? new(app) : nil
      end

      def self.create(**)
        FakeASC.write("App.create")
      end

      def get_app_store_versions(client: nil, filter: {}, includes: nil, limit: nil, sort: nil)
        FakeASC.call("App#get_app_store_versions", filter: filter)
        versions = @data["versions"].map { |data| AppStoreVersion.new(data) }
        return versions if FakeASC::SCENARIO["ignore_filter"]

        versions.select do |version|
          version.version_string == filter[:versionString] && version.platform == filter[:platform]
        end
      end

      def get_in_progress_review_submission(platform:, client: nil, includes: nil)
        FakeASC.call("App#get_in_progress_review_submission", platform: platform)
        @data["review_submission"] ? FakeASC::Model.new({ "id" => "submission-1" }) : nil
      end

      # Like fastlane, this also returns an app info that is waiting for review.
      def fetch_edit_app_info(client: nil, includes: nil)
        FakeASC.call("App#fetch_edit_app_info")
        info = @data["app_info"]
        info && EDIT_APP_INFO_STATES.include?(info["state"]) ? AppInfo.new(info) : nil
      end

      EDIT_APP_INFO_STATES = %w[PREPARE_FOR_SUBMISSION DEVELOPER_REJECTED REJECTED WAITING_FOR_REVIEW].freeze
    end

    class AppStoreVersion < FakeASC::Model
      reads :version_string, :platform, :app_version_state, :app_store_state
      writes :update, :select_build, :create_app_store_version_localization,
             :create_app_store_version_submission, :create_app_store_version_release_request, :reject!

      def get_build(client: nil, build_id: nil)
        FakeASC.call("AppStoreVersion#get_build")
        @data["build"] && Build.new(@data["build"])
      end

      def get_app_store_version_localizations(client: nil, filter: {}, includes: nil, limit: nil, sort: nil)
        FakeASC.call("AppStoreVersion#get_app_store_version_localizations", limit: limit)
        @data["localizations"].map { |data| AppStoreVersionLocalization.new(data) }
      end
    end

    class Build < FakeASC::Model
      reads :version, :processing_state
    end

    class AppInfo < FakeASC::Model
      reads :state
      writes :update, :create_app_info_localization, :delete!

      def get_app_info_localizations(client: nil, filter: {}, includes: nil, limit: nil, sort: nil)
        FakeASC.call("AppInfo#get_app_info_localizations", limit: limit)
        @data["localizations"].map { |data| AppInfoLocalization.new(data) }
      end
    end

    class AppInfoLocalization < FakeASC::Model
      reads :locale, :name, :subtitle, :privacy_policy_url
      writes :update, :delete!
    end

    class AppStoreVersionLocalization < FakeASC::Model
      reads :locale, :description, :keywords, :promotional_text, :whats_new, :support_url, :marketing_url
      writes :update, :delete!, :create_app_screenshot_set, :create_app_preview_set

      def get_app_screenshot_sets(client: nil, filter: {}, includes: "appScreenshots", limit: nil, sort: nil)
        FakeASC.call("AppStoreVersionLocalization#get_app_screenshot_sets", locale: locale, limit: limit)
        @data["sets"].map { |data| AppScreenshotSet.new(data) }
      end
    end

    class AppScreenshotSet < FakeASC::Model
      reads :screenshot_display_type
      writes :delete!, :upload_screenshot, :reorder_screenshots

      def app_screenshots
        @data["screenshots"].map { |data| AppScreenshot.new(data) }
      end
    end

    class AppScreenshot < FakeASC::Model
      reads :asset_delivery_state, :image_asset, :source_file_checksum, :file_size, :file_name
      writes :delete!

      def self.create(**)
        FakeASC.write("AppScreenshot.create")
      end
    end
  end
end
