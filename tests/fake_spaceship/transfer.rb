# Opt-in write fake. Never loaded by snapshot/read-only fixtures.
require "digest"

module FakeASC
  class << self
    alias_method :call_without_tamper, :call

    def call(name, **arguments)
      call_without_tamper(name, **arguments)
      if (tamper = SCENARIO["tamper_stage"]) && name == tamper
        files = Dir.glob(File.join(ENV.fetch("TMPDIR"), "app-store-assets-transfer-*", "*"))
        raise "tamper fixture found no staged files" if files.empty?

        File.binwrite(files.sort.last, "changed staged bytes")
      end
    end
  end

  def self.sets
    SCENARIO["app"]["versions"].flat_map { |v| v["localizations"].flat_map { |l| l["sets"] } }
  end

  def self.transfer_write(name, **arguments)
    call(name, **arguments, request_timeout: ENV["SPACESHIP_TIMEOUT"],
         upload_timeout: ENV["SPACESHIP_SCREENSHOT_UPLOAD_TIMEOUT"])
  end

  at_exit do
    File.write(ENV.fetch("FAKE_ASC_ENV_LOG"), JSON.generate(
      request: ENV["SPACESHIP_TIMEOUT"], upload: ENV["SPACESHIP_SCREENSHOT_UPLOAD_TIMEOUT"]
    )) if ENV["FAKE_ASC_ENV_LOG"]
  end
end

module Spaceship
  module ConnectAPI
    class AppStoreVersionLocalization
      def create_app_screenshot_set(client: nil, attributes: nil)
        FakeASC.transfer_write("create", locale: locale, slot: attributes.fetch(:screenshotDisplayType))
        data = { "id" => "new-#{locale}", "screenshot_display_type" => attributes.fetch(:screenshotDisplayType), "screenshots" => [] }
        @data["sets"] << data
        AppScreenshotSet.new(data)
      end
    end

    class AppScreenshotSet
      def self.get(client: nil, app_screenshot_set_id: nil, includes: "appScreenshots")
        FakeASC.call("poll", set: app_screenshot_set_id)
        data = FakeASC.sets.find { |s| s["id"] == app_screenshot_set_id }
        data["polls"] = data.fetch("polls", 0) + 1
        if (after = FakeASC::SCENARIO["settle_after"]) && data["polls"] >= after
          data["screenshots"].each do |s|
            s["asset_delivery_state"] = { "state" => "COMPLETE" }
            s["source_file_checksum"] = s["expected_md5"] if s["expected_md5"]
          end
        end
        if FakeASC::SCENARIO["poll_change_id"] && !data["screenshots"].empty?
          data["screenshots"].first["id"] = "foreign-during-poll"
        end
        if FakeASC::SCENARIO["reverse"] && !data["reversed"] && data["screenshots"].size > 1
          data["screenshots"].reverse!
          data["reversed"] = true
        end
        new(data)
      end

      def upload_screenshot(client: nil, path: nil, wait_for_processing: true, position: nil)
        bytes = File.binread(path)
        md5 = Digest::MD5.hexdigest(bytes)
        FakeASC.transfer_write("upload", set: id, path: path, sha256: Digest::SHA256.hexdigest(bytes),
                               position: position, wait_for_processing: wait_for_processing)
        behavior = FakeASC::SCENARIO
        if behavior["placeholder_retry"]
          loop { puts "waiting for placeholder"; sleep 0.02 }
        end
        screenshot = { "id" => "uploaded-#{id}-#{position}", "expected_md5" => md5,
                       "source_file_checksum" => behavior.fetch("checksum", md5),
                       "asset_delivery_state" => { "state" => behavior.fetch("processing", "COMPLETE") },
                       "image_asset" => { "width" => 1242, "height" => 2688 } }
        @data["screenshots"].insert(position, screenshot)
        sleep 10 if behavior["upload_timeout"]
        sleep behavior["upload_delay"] if behavior["upload_delay"]
        FakeASC.call("uploaded", set: id, position: position)
        AppScreenshot.new(screenshot)
      end

      def reorder_screenshots(client: nil, app_screenshot_ids: nil)
        FakeASC.transfer_write("reorder", set: id, ids: app_screenshot_ids)
        unless FakeASC::SCENARIO["ignore_reorder"]
          @data["screenshots"] = app_screenshot_ids.map { |sid| @data["screenshots"].find { |s| s["id"] == sid } }
        end
        self
      end
    end

    class AppScreenshot
      def delete!(client: nil, filter: {}, includes: nil, limit: nil, sort: nil)
        FakeASC.transfer_write("delete", id: id)
        FakeASC.sets.each { |s| s["screenshots"].reject! { |image| image["id"] == id } }
      end
    end
  end
end

# Reproduce changes between per-group readback and the final whole-target read.
Spaceship::ConnectAPI::App.singleton_class.prepend(Module.new do
  def find(*)
    @reads = (@reads || 0) + 1
    if @reads == 2 && (change = FakeASC::SCENARIO["final_change"])
      version = FakeASC::SCENARIO["app"]["versions"].first
      case change
      when "build" then version["build"]["version"] = "999"
      when "state" then version["app_version_state"] = "IN_REVIEW"
      when "preserved" then version["localizations"][0]["sets"][1]["screenshots"][0]["id"] = "foreign"
      when "declared" then version["localizations"][0]["sets"][0]["screenshots"].first["source_file_checksum"] = "0" * 32
      when "set_id" then version["localizations"][0]["sets"][1]["id"] = "foreign-set"
      when "declared_id" then version["localizations"][0]["sets"][0]["screenshots"].first["id"] = "foreign-shot"
      when "review" then FakeASC::SCENARIO["app"]["review_submission"] = true
      end
    end
    super
  end
end)
