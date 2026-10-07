# Store effects are only reached after explicit authority and staged plan checks.
# Loading this file does not load an SDK, authenticate, or make a remote request.
require "json"
require "digest"
require "pathname"
require "fileutils"

module StoreProvider
  def self.sorted(value)
    return value.keys.sort.to_h { |k| [k, sorted(value[k])] } if value.is_a?(Hash)
    return value.map { |v| sorted(v) } if value.is_a?(Array)
    value
  end

  def self.digest(value)
    Digest::SHA256.hexdigest(JSON.generate(sorted(value)) + "\n")
  end

  def self.snapshot_record(target, body)
    record = {"schema_version" => 1, "type" => "metadata-snapshot", "origin" => "remote", "target" => target}.merge(body)
    record["revision"] = digest(record)
    record
  end

  def self.path(root, relative, sha256 = nil)
    parts = relative.split("/")
    raise "invalid staged path" if relative.start_with?("/") || parts.any? { |p| ["", ".", ".."].include?(p) }
    current = File.expand_path(root)
    parts.each do |part|
      current = File.join(current, part)
      raise "staged symlink rejected" if File.symlink?(current)
    end
    raise "staged input missing" unless File.file?(current)
    raise "staged hash differs" if sha256 && Digest::SHA256.file(current).hexdigest != sha256
    current
  end

  def self.guard(payload, observed)
    raise "remote snapshot/version changed" unless payload.fetch("remote") == observed
    raise "remote target differs" unless observed.fetch("target") == payload.fetch("target")
    if payload.fetch("operation") == "images"
      desired = payload.fetch("listing").fetch("images")
      policy = payload["replacement"]
      raise "replacement policy is missing" unless policy && !desired.empty?
      local_groups = desired.flat_map { |locale, groups| groups.keys.map { |slot| [locale, slot] } }
      remote_groups = observed.fetch("images").flat_map do |locale, groups|
        groups.select { |_, images| !images.empty? }.keys.map { |slot| [locale, slot] }
      end
      raise "remote class/locale omitted" unless (remote_groups - local_groups).empty?
      raise "deleting existing screenshots requires explicit reviewed allow_delete policy" unless remote_groups.empty? || policy["allow_delete"] == true
      raise "replacement locale differs" unless policy.fetch("locales").sort == local_groups.map(&:first).uniq.sort
      raise "replacement slot differs" unless policy.fetch("slots").sort == local_groups.map(&:last).uniq.sort
    end
  end

  def self.download_image(url, destination)
    require "net/http"
    require "uri"
    uri = URI(url)
    raise "image download requires HTTPS without embedded credentials" unless uri.is_a?(URI::HTTPS) && !uri.userinfo
    response = Net::HTTP.start(uri.host, uri.port, use_ssl: true, open_timeout: 30, read_timeout: 60) do |http|
      http.get(uri.request_uri)
    end
    raise "image download failed" unless response.is_a?(Net::HTTPSuccess)
    raise "image download exceeds bound" if response.body.bytesize > 32 * 1024 * 1024
    bytes = response.body
    extension = bytes.start_with?("\x89PNG\r\n\x1a\n".b) ? ".png" : (bytes.start_with?("\xff\xd8\xff".b) ? ".jpg" : nil)
    raise "remote image format unsupported" unless extension
    destination += extension
    FileUtils.mkdir_p(File.dirname(destination))
    File.binwrite(destination, bytes)
    destination
  end

  class Apple
    VERSION_FIELDS = {"description" => "description", "keywords" => "keywords", "promotional_text" => "promotional_text",
                      "release_notes" => "whats_new", "support_url" => "support_url", "marketing_url" => "marketing_url"}.freeze
    INFO_FIELDS = {"name" => "name", "subtitle" => "subtitle", "privacy_url" => "privacy_policy_url"}.freeze
    EDITABLE = %w(PREPARE_FOR_SUBMISSION DEVELOPER_REJECTED REJECTED METADATA_REJECTED).freeze
    REVIEW = %w(WAITING_FOR_REVIEW IN_REVIEW PENDING_APPLE_RELEASE PENDING_DEVELOPER_RELEASE).freeze

    def initialize(app, app_info: nil)
      @app, @app_info = app, app_info
    end

    def version(target)
      raise "Apple bundle/account target differs" unless @app.bundle_id == target.fetch("app_id")
      platform = target.fetch("platform") == "macos" ? "MAC_OS" : "IOS"
      matches = @app.get_app_store_versions(filter: {"versionString" => target.fetch("version").fetch("name"), "platform" => platform})
                    .select { |v| v.version_string == target.fetch("version").fetch("name") }
      raise "ambiguous exact Apple version" if matches.length > 1
      matches.first
    end

    def snapshot(target)
      selected = version(target)
      fields, images = {}, {}
      if selected
        selected.get_app_store_version_localizations.each do |locale|
          fields[locale.locale] = VERSION_FIELDS.to_h { |key, method| [key, locale.respond_to?(method) ? locale.public_send(method).to_s : ""] }
          images[locale.locale] = locale.get_app_screenshot_sets.to_h do |set|
            [set.screenshot_display_type, (set.app_screenshots || []).map do |image|
              {"id" => image.id, "processing_state" => image.asset_delivery_state&.fetch("state", nil) == "COMPLETE" ? "processed" : "pending"}
            end]
          end
        end
      end
      if @app_info
        @app_info.get_app_info_localizations.each do |locale|
          fields[locale.locale] ||= {}
          INFO_FIELDS.each { |key, method| fields[locale.locale][key] = locale.public_send(method).to_s }
        end
      end
      builds = @app.get_builds(filter: {"version" => target.fetch("version").fetch("build")}, includes: "preReleaseVersion")
      exact = builds.select { |b| b.version.to_s == target["version"]["build"] && b.pre_release_version&.version == target["version"]["name"] }
      raise "ambiguous Apple build" if exact.length > 1
      binary = exact.first && {"app_id" => target["app_id"], "version" => {"name" => exact.first.pre_release_version.version,
                 "build" => exact.first.version.to_s}, "processing_state" => exact.first.processing_state == "VALID" ? "processed" : "pending",
                 "source_sha256" => nil}
      StoreProvider.snapshot_record(target, {"version_id" => selected&.id, "app_info_id" => @app_info&.id,
        "editable" => selected && EDITABLE.include?(selected.app_store_state),
        "review_active" => selected && REVIEW.include?(selected.app_store_state),
        "fields" => fields, "images" => images, "binary" => binary, "effects" => ["read"]})
    end

    def upload(plan, root)
      payload = plan.fetch("payload")
      target = payload.fetch("target")
      current = snapshot(target)
      StoreProvider.guard(payload, current)
      operation = payload.fetch("operation")
      if operation == "binary"
        raise "existing Apple build blocks duplicate transfer" if current["binary"]
        raise "Apple binary localized notes need a separate beta-localization adapter" unless payload.fetch("release_notes", {}).empty?
        descriptor = payload.fetch("artifact")
        artifact = StoreProvider.path(root, descriptor.fetch("path"), payload.fetch("build").fetch("sha256"))
        require "pilot"
        options = {ipa: artifact, app_identifier: target.fetch("app_id"), apple_id: @app.id,
          api_key_path: @auth_file, skip_submission: true, skip_waiting_for_build_processing: true,
          distribute_external: false, notify_external_testers: false}
        config = FastlaneCore::Configuration.create(Pilot::Options.available_options, options)
        Pilot::BuildManager.new.upload(config)
        return {"accepted" => true, "remote_ids" => []}
      end
      raise "Apple exact listing version is not editable" unless current["version_id"] && current["editable"] && !current["review_active"]
      selected = version(target)
      raise "Apple write version ID differs" unless selected.id == payload.fetch("remote").fetch("version_id")
      localizations = selected.get_app_store_version_localizations.to_h { |l| [l.locale, l] }
      if operation == "metadata"
        fields = payload.fetch("listing").fetch("fields")
        fields.each do |locale, values|
          raise "create locale needs a separately scoped plan" unless localizations[locale]
          raise "unsupported Apple metadata field" unless (values.keys - VERSION_FIELDS.keys - INFO_FIELDS.keys).empty?
          raise "exact editable app-info snapshot required" if (values.keys & INFO_FIELDS.keys).any? && (!@app_info || @app_info.id != current["app_info_id"])
        end
        fields.each do |locale, values|
          attrs = values.select { |k, _| VERSION_FIELDS.key?(k) }.to_h { |k, v| [VERSION_FIELDS[k], v] }
          localizations.fetch(locale).update(attributes: attrs) unless attrs.empty?
          attrs = values.select { |k, _| INFO_FIELDS.key?(k) }.to_h { |k, v| [INFO_FIELDS[k], v] }
          unless attrs.empty?
            info = @app_info.get_app_info_localizations.find { |l| l.locale == locale }
            raise "missing exact app-info localization" unless info
            info.update(attributes: attrs)
          end
        end
        return {"accepted" => true, "remote_ids" => [selected.id]}
      end
      raise "unsupported Apple operation" unless operation == "images"
      require "deliver/app_screenshot"
      groups = payload.fetch("listing").fetch("images")
      groups.each do |locale, slots|
        raise "missing Apple locale" unless localizations[locale]
        slots.each do |slot, images|
          images.each do |image|
            path = StoreProvider.path(root, image.fetch("file"), image.fetch("sha256"))
            reader = Deliver::AppScreenshot.new(path, locale)
            raise "Fastlane display type differs from manifest" unless reader.display_type == slot
          end
        end
      end
      ids = {}
      groups.each do |locale, slots|
        ids[locale] = {}
        slots.each do |slot, images|
          localization = localizations.fetch(locale)
          set = localization.get_app_screenshot_sets.find { |s| s.screenshot_display_type == slot }
          set ||= localization.create_app_screenshot_set(attributes: {screenshotDisplayType: slot})
          (set.app_screenshots || []).each(&:delete!)
          ids[locale][slot] = images.map do |image|
            set.upload_screenshot(path: StoreProvider.path(root, image.fetch("file"), image.fetch("sha256")), wait_for_processing: false).id
          end
          set.reorder_screenshots(app_screenshot_ids: ids[locale][slot])
        end
      end
      {"accepted" => true, "remote_ids" => [selected.id], "image_ids" => ids}
    end

    attr_writer :auth_file

    def readback(plan, _result)
      payload = plan.fetch("payload")
      observed = snapshot(payload.fetch("target"))
      {"target" => observed.fetch("target"), "observed" => {"binary" => observed["binary"],
         "fields" => observed["fields"], "images" => observed["images"], "release_notes" => {}}}
    end

    def download(target, output)
      record = snapshot(target)
      selected = version(target)
      raise "exact Apple listing version is missing" unless selected
      selected.get_app_store_version_localizations.each do |locale|
        locale.get_app_screenshot_sets.each do |set|
          (set.app_screenshots || []).each_with_index do |image, index|
            asset = image.image_asset
            raise "remote screenshot download metadata missing" unless asset && asset["templateUrl"]
            raise "unsafe remote locale/slot identifier" unless [locale.locale, set.screenshot_display_type].all? { |s| s.match?(/\A[A-Za-z0-9_-]+\z/) }
            url = asset["templateUrl"].gsub("{w}", asset.fetch("width").to_s).gsub("{h}", asset.fetch("height").to_s).gsub("{f}", "png")
            path = StoreProvider.download_image(url, File.join(output, "images", locale.locale, set.screenshot_display_type, format("%02d", index + 1)))
            item = record.fetch("images").fetch(locale.locale).fetch(set.screenshot_display_type)[index]
            item["file"] = Pathname.new(path).relative_path_from(Pathname.new(output)).to_s
            item["sha256"] = Digest::SHA256.file(path).hexdigest
          end
        end
      end
      {"record" => record}
    end
  end

  class Google
    IMAGE_TYPES = %w(phoneScreenshots sevenInchScreenshots tenInchScreenshots tvScreenshots wearScreenshots icon featureGraphic tvBanner).freeze
    def initialize(client); @client = client; end

    def read_session(target)
      @client.begin_edit(package_name: target.fetch("app_id"))
      begin
        yield
      ensure
        @client.abort_current_edit
      end
    end

    def state_in_edit(target)
        fields, images = {}, {}
        @client.listings.each do |listing|
          locale = listing.language
          fields[locale] = %w(title short_description full_description video).to_h { |k| [k, listing.public_send(k).to_s] }
          images[locale] = IMAGE_TYPES.to_h do |slot|
            [slot, @client.fetch_images(image_type: slot, language: locale).map do |image|
              {"id" => image.id, "provider_sha256" => image.sha256, "processing_state" => "processed"}
            end]
          end
        end
        releases = @client.track_releases(target.fetch("track")).map do |r|
          {"name" => r.name, "status" => r.status, "version_codes" => r.version_codes.map(&:to_s),
           "notes" => (r.release_notes || []).to_h { |n| [n.language, n.text] }}
        end
        all_codes = (@client.aab_version_codes + @client.apks_version_codes).map(&:to_s)
        StoreProvider.snapshot_record(target, {"fields" => fields, "images" => images, "releases" => releases,
          "build_exists" => all_codes.include?(target.fetch("version").fetch("build")), "effects" => ["read", "open-read-session"]})
    end

    def snapshot(target)
      read_session(target) { state_in_edit(target) }
    end

    def upload(plan, root)
      payload, target = plan.fetch("payload"), plan.fetch("payload").fetch("target")
      StoreProvider.guard(payload, snapshot(target))
      @client.begin_edit(package_name: target.fetch("app_id"))
      committed = false
      image_ids = {}
      begin
        # Compare inside the write edit as well; do not rely on a prior read session.
        StoreProvider.guard(payload, state_in_edit(target))
        if payload.fetch("operation") == "binary"
          raise "Google duplicate versionCode" if (@client.aab_version_codes + @client.apks_version_codes).map(&:to_s).include?(target["version"]["build"])
          raise "unsupported rollout/release status" unless %w(draft completed).include?(payload.fetch("release_status"))
          require "google/apis/androidpublisher_v3"
          artifact = StoreProvider.path(root, payload.fetch("artifact").fetch("path"), payload.fetch("build").fetch("sha256"))
          uploaded = @client.upload_bundle(artifact)
          raise "uploaded Google versionCode differs" unless uploaded.version_code.to_s == target["version"]["build"]
          notes = payload.fetch("release_notes", {}).map { |locale, text| ::Google::Apis::AndroidpublisherV3::LocalizedText.new(language: locale, text: text) }
          release = ::Google::Apis::AndroidpublisherV3::TrackRelease.new(name: target["version"]["name"], status: payload.fetch("release_status"),
            version_codes: [target["version"]["build"].to_i], release_notes: notes)
          prior = payload.fetch("release_status") == "draft" ? @client.track_releases(target.fetch("track")) : []
          track = ::Google::Apis::AndroidpublisherV3::Track.new(track: target.fetch("track"), releases: prior + [release])
          @client.update_track(target.fetch("track"), track)
        elsif payload.fetch("operation") == "metadata"
          fields = payload.fetch("listing").fetch("fields")
          fields.each_value { |values| raise "unsupported Google metadata field" unless (values.keys - %w(title short_description full_description description video)).empty? }
          fields.each do |locale, values|
            listing = @client.listing_for_language(locale)
            values.each { |k, v| listing.public_send((k == "description" ? "full_description" : k) + "=", v) }
            listing.save
          end
        elsif payload.fetch("operation") == "images"
          groups = payload.fetch("listing").fetch("images")
          groups.each_value do |slots|
            slots.each do |slot, images|
              raise "unsupported Google image API slot" unless IMAGE_TYPES.include?(slot)
              images.each { |image| StoreProvider.path(root, image.fetch("file"), image.fetch("sha256")) }
            end
          end
          groups.each do |locale, slots|
            image_ids[locale] = {}
            slots.each do |slot, images|
              @client.clear_screenshots(image_type: slot, language: locale)
              image_ids[locale][slot] = images.map do |image|
                response = @client.upload_image(image_path: StoreProvider.path(root, image.fetch("file"), image.fetch("sha256")), image_type: slot, language: locale)
                raise "Google image upload ID missing" unless response.image && response.image.id
                response.image.id
              end
            end
          end
        else
          raise "unsupported Google operation"
        end
        @client.validate_current_edit!
        @client.commit_current_edit!
        committed = true
        {"accepted" => true, "remote_ids" => [], "image_ids" => image_ids}
      ensure
        @client.abort_current_edit unless committed
      end
    end

    def readback(plan, _result)
      payload = plan.fetch("payload")
      current = snapshot(payload.fetch("target"))
      target = payload.fetch("target")
      release = current.fetch("releases").find { |r| r.fetch("version_codes").include?(target["version"]["build"]) }
      binary = release && {"app_id" => target["app_id"], "version" => {"name" => release["name"], "build" => target["version"]["build"]},
                           "source_sha256" => nil, "processing_state" => current["build_exists"] ? "processed" : "pending"}
      {"target" => target, "observed" => {"binary" => binary, "release_status" => release && release["status"],
        "release_notes" => release && release["notes"], "fields" => current["fields"], "images" => current["images"]}}
    end

    def download(target, output)
      record = snapshot(target)
      read_session(target) do
        @client.listings.each do |listing|
          IMAGE_TYPES.each do |slot|
            @client.fetch_images(image_type: slot, language: listing.language).each_with_index do |image, index|
              raise "unsafe remote locale" unless listing.language.match?(/\A[A-Za-z0-9_-]+\z/)
              path = StoreProvider.download_image(image.url, File.join(output, "images", listing.language, slot, format("%02d", index + 1)))
              item = record.fetch("images").fetch(listing.language).fetch(slot)[index]
              raise "download image inventory changed" unless item["id"] == image.id
              item["file"] = Pathname.new(path).relative_path_from(Pathname.new(output)).to_s
              item["sha256"] = Digest::SHA256.file(path).hexdigest
            end
          end
        end
      end
      {"record" => record}
    end
  end

  def self.run(request)
    raise "explicit live authorization required" unless request["authorized"] == true && request["mode"] == "live" && request["auth_file"]
    target = request.fetch("target")
    raise "native provider not available; use a separately reviewed account-bound command adapter" unless %w(apple google).include?(target["store"])
    raise "explicit account binding required" unless target["account_id"]
    auth_file = request.fetch("auth_file")
    # This protected read is unreachable from doctor/plan/dry-run/fixture mode.
    auth = JSON.parse(File.read(auth_file))
    require "fastlane/version"
    raise "Fastlane 2.240.1 required" unless Fastlane::VERSION == "2.240.1"
    if target.fetch("store") == "apple"
      raise "Apple issuer/account differs" unless auth["issuer_id"] == target["account_id"]
      require "spaceship"
      Spaceship::ConnectAPI.token = Spaceship::ConnectAPI::Token.from_json_file(auth_file)
      app = Spaceship::ConnectAPI::App.find(target.fetch("app_id"))
      raise "Apple app unavailable in authorized account" unless app && app.bundle_id == target["app_id"]
      infos = Spaceship::ConnectAPI.get_app_infos(app_id: app.id).to_models.select { |i| Apple::EDITABLE.include?(i.state) }
      raise "ambiguous editable app-info" if infos.length > 1
      provider = Apple.new(app, app_info: infos.first)
      provider.auth_file = auth_file
    elsif target.fetch("store") == "google"
      raise "Google service account differs" unless auth["client_email"] == target["account_id"]
      require "supply"
      Supply.config = FastlaneCore::Configuration.create(Supply::Options.available_options, {json_key: auth_file,
        package_name: target.fetch("app_id"), track: target.fetch("track"), release_status: request.dig("plan", "payload", "release_status") || "draft",
        changes_not_sent_for_review: true, rescue_changes_not_sent_for_review: false})
      provider = Google.new(Supply::Client.make_from_config)
    else
      raise "native provider not available; use a separately reviewed account-bound command adapter"
    end
    case request.fetch("action")
    when "snapshot" then provider.snapshot(target)
    when "download" then provider.download(target, request.fetch("output"))
    when "readback" then provider.readback(request.fetch("plan"), request.fetch("result"))
    when "upload"
      plan = request.fetch("plan")
      raise "provider plan digest differs" unless digest(plan.fetch("payload")) == plan.fetch("digest")
      provider.upload(plan, request.fetch("root"))
    else raise "unsupported provider action"
    end
  end
end

if $PROGRAM_NAME == __FILE__
  begin
    request = JSON.parse($stdin.read)
    result = StoreProvider.run(request)
    puts JSON.generate(result)
  rescue => error
    # Never export SDK errors, auth JSON, signed URLs, or raw response bodies.
    warn "Store provider blocked or failed (#{error.class}); explicit authorization/account/target and SDK availability are required."
    exit 1
  end
end
