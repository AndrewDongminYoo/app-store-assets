require "json"
require "open3"
require "digest"
require "securerandom"
require "timeout"

module AppStoreAssets
  # A prepared path is not authorization to replace remote screenshots.
  # Local preparation is not authorization for a remote transfer.
  def self.prepare(**)
    raise "Legacy screenshot transfer blocked: a reviewed plan and digest are required for any transfer. " \
          "Use AppStoreAssets.prepare_local only for local preparation."
  end

  def self.prepare_local(repo_root:, project:, bundle_id:, source:, subdir: ".", normalize_alpha: false)
    command = [ENV.fetch("PYTHON", "python3"), File.expand_path("../assets.py", __dir__),
               "prepare-screenshots", "--source", source,
               "--out", File.join(repo_root, "build/store-assets/ios-bundles"),
               "--project", project, "--bundle-id", bundle_id, "--subdir", subdir]
    command << "--normalize-alpha" if normalize_alpha
    output, errors, result = Open3.capture3(*command)
    raise "App Store screenshot preparation failed: #{errors.strip}" unless result.success?

    bundle = JSON.parse(output)
    { screenshots_path: bundle.fetch("screenshots_path") }
  end

  SNAPSHOT_IDENTITY_KEYS = %w[store platform account account_id app_id flavor stage version].freeze
  SNAPSHOT_REQUIRED_KEYS = (SNAPSHOT_IDENTITY_KEYS - %w[account_id]).freeze
  # Version states in which App Store Connect accepts screenshot and text edits.
  # WAITING_FOR_REVIEW is excluded: the version must leave review before an edit.
  SNAPSHOT_EDITABLE_STATES = %w[
    PREPARE_FOR_SUBMISSION DEVELOPER_REJECTED REJECTED METADATA_REJECTED INVALID_BINARY
  ].freeze
  SNAPSHOT_REVIEW_STATES = %w[WAITING_FOR_REVIEW IN_REVIEW].freeze
  # App info states in which App Store Connect accepts name, subtitle and privacy URL edits.
  SNAPSHOT_APP_INFO_EDITABLE_STATES = %w[PREPARE_FOR_SUBMISSION DEVELOPER_REJECTED REJECTED].freeze
  # App Store Connect's maximum page size; a full page may be truncated.
  SNAPSHOT_PAGE_LIMIT = 200
  SNAPSHOT_DEFAULT_DEADLINE = 120
  SNAPSHOT_MAX_DEADLINE = 600
  SNAPSHOT_VALIDATOR = <<~PYTHON.freeze
    import json, sys
    sys.path.insert(0, sys.argv[1])
    from app_store_assets.metadata import remote_observation, validate_public_metadata
    record = json.loads(sys.stdin.read())
    if record.get("type") != "metadata-snapshot":
        raise SystemExit("record is not a metadata-snapshot")
    validate_public_metadata(record, record["target"])
    remote_observation(record)
  PYTHON

  # Reads the App Store Connect state of one Apple iOS target and writes one
  # metadata-snapshot record. Call it only after the lane has authenticated Spaceship.
  # It makes no remote write and never replaces an existing file.
  def self.export_snapshot(target:, output:, deadline: SNAPSHOT_DEFAULT_DEADLINE)
    identity = snapshot_target(target)
    unless deadline.is_a?(Numeric) && deadline.positive? && deadline <= SNAPSHOT_MAX_DEADLINE
      raise snapshot_error("deadline must be more than 0 and at most #{SNAPSHOT_MAX_DEADLINE} seconds")
    end

    output = snapshot_output(output)
    record = nil
    original_stdout = $stdout
    saved_stdout = STDOUT.dup
    begin
      # Provider output goes to standard error; standard output carries one result.
      # Reopening STDOUT also moves writers that hold the STDOUT object itself, such as
      # Spaceship's VERBOSE request logger, even one built earlier, at login.
      STDOUT.flush
      STDOUT.reopen(STDERR)
      $stdout = $stderr
      begin
        require "spaceship"
      rescue LoadError
        raise snapshot_error("Spaceship is unavailable; call this from an authenticated Fastlane lane")
      end
      record = snapshot_record(identity, deadline)
    ensure
      STDOUT.flush
      STDOUT.reopen(saved_stdout)
      saved_stdout.close
      $stdout = original_stdout
    end
    data = JSON.pretty_generate(record) + "\n"
    snapshot_validate(data)
    snapshot_publish(output, data)
    result = {
      output: output,
      sha256: Digest::SHA256.hexdigest(data),
      counts: {
        locales: record["images"].size,
        screenshot_sets: record["images"].values.sum(&:size),
        screenshots: record["images"].values.sum { |sets| sets.values.sum(&:size) }
      }
    }
    $stdout.puts(JSON.generate(result))
    $stdout.flush
    result
  end

  def self.snapshot_error(message)
    RuntimeError.new("App Store snapshot export refused: #{message}")
  end

  def self.snapshot_strings(value)
    case value
    when Hash then value.to_h { |key, item| [key.to_s, snapshot_strings(item)] }
    when Array then value.map { |item| snapshot_strings(item) }
    else value
    end
  end

  def self.snapshot_target(target)
    raise snapshot_error("target must be a hash") unless target.is_a?(Hash)

    identity = snapshot_strings(target)
    unknown = identity.keys - SNAPSHOT_IDENTITY_KEYS
    missing = SNAPSHOT_REQUIRED_KEYS - identity.keys
    raise snapshot_error("unknown target keys: #{unknown.sort.join(', ')}") unless unknown.empty?
    raise snapshot_error("missing target keys: #{missing.sort.join(', ')}") unless missing.empty?
    unless identity["store"] == "apple" && identity["platform"] == "ios"
      raise snapshot_error("only store apple with platform ios is supported")
    end

    version = identity["version"]
    unless version.is_a?(Hash) && version.keys.sort == %w[build name] &&
           version["name"].is_a?(String) && version["name"].match?(/\A[0-9]+(?:\.[0-9]+){0,3}\z/) &&
           version["build"].is_a?(String) && version["build"].match?(/\A[0-9]+\z/)
      raise snapshot_error("target version requires a numeric name and build")
    end
    unless identity["app_id"].is_a?(String) && identity["app_id"].match?(/\A[A-Za-z0-9_.-]+\z/)
      raise snapshot_error("target app_id must be a bundle identifier")
    end

    identity
  end

  def self.snapshot_checkout
    File.realpath(File.expand_path("..", __dir__))
  end

  def self.snapshot_output(output)
    raise snapshot_error("output must be an absolute path") unless output.is_a?(String) && output.start_with?("/")

    # lstat also sees a dangling symbolic link, which File.exist? does not.
    exists = begin
      File.lstat(output)
      true
    rescue Errno::ENOENT, Errno::ENOTDIR
      false
    end
    raise snapshot_error("output already exists: #{output}") if exists

    begin
      parent = File.realpath(File.dirname(output))
    rescue SystemCallError
      raise snapshot_error("output directory does not exist: #{File.dirname(output)}")
    end
    raise snapshot_error("output directory is not a directory: #{parent}") unless File.directory?(parent)

    checkout = snapshot_checkout
    if parent == checkout || parent.start_with?(checkout + "/")
      raise snapshot_error("output must stay outside the app-store-assets checkout")
    end

    File.join(parent, File.basename(output))
  end

  # Every provider call, including Spaceship's own 429 backoff and retries, ends at the deadline.
  def self.snapshot_call(label, deadline, &block)
    Timeout.timeout(deadline, &block)
  rescue Timeout::Error
    raise snapshot_error("provider call exceeded the #{deadline}-second deadline: #{label}")
  end

  def self.snapshot_page(label, items)
    items = Array(items)
    raise snapshot_error("#{label} returned a full page and may be truncated") if items.size >= SNAPSHOT_PAGE_LIMIT

    items
  end

  def self.snapshot_record(identity, deadline)
    api = Spaceship::ConnectAPI
    bundle_id = identity["app_id"]
    name = identity["version"]["name"]

    app = snapshot_call("app", deadline) { api::App.find(bundle_id) }
    raise snapshot_error("no App Store Connect app for #{bundle_id}") if app.nil?

    versions = snapshot_call("app store versions", deadline) do
      app.get_app_store_versions(filter: { versionString: name, platform: "IOS" })
    end
    matches = Array(versions).select { |item| item.version_string == name && item.platform == "IOS" }
    raise snapshot_error("no iOS App Store version #{name} for #{bundle_id}") if matches.empty?
    raise snapshot_error("more than one iOS App Store version #{name} for #{bundle_id}") if matches.size > 1

    version = matches.first
    raise snapshot_error("App Store version #{name} has no ID") unless version.id.is_a?(String) && !version.id.empty?

    state = version.app_version_state || version.app_store_state
    submission = snapshot_call("review submission", deadline) do
      app.get_in_progress_review_submission(platform: "IOS")
    end
    build = snapshot_call("attached build", deadline) { version.get_build }
    app_info = snapshot_call("app info", deadline) { app.fetch_edit_app_info }
    # fetch_edit_app_info also returns an app info in WAITING_FOR_REVIEW, which accepts no edit.
    app_info = nil unless app_info.nil? || SNAPSHOT_APP_INFO_EDITABLE_STATES.include?(app_info.state)

    fields = {}
    if app_info
      infos = snapshot_call("app info localizations", deadline) do
        app_info.get_app_info_localizations(limit: SNAPSHOT_PAGE_LIMIT)
      end
      snapshot_page("app info localizations", infos).each do |info|
        raise snapshot_error("duplicate app info locale #{info.locale}") if fields.key?(info.locale)

        fields[info.locale] = {
          "name" => info.name.to_s,
          "subtitle" => info.subtitle.to_s,
          "privacy_url" => info.privacy_policy_url.to_s
        }
      end
    end

    images = {}
    localizations = snapshot_call("version localizations", deadline) do
      version.get_app_store_version_localizations(limit: SNAPSHOT_PAGE_LIMIT)
    end
    snapshot_page("version localizations", localizations).each do |localization|
      locale = localization.locale
      raise snapshot_error("duplicate version locale #{locale}") if images.key?(locale)

      # validate_apple_localizations needs every version field, even an empty one.
      (fields[locale] ||= {}).merge!(
        "description" => localization.description.to_s,
        "keywords" => localization.keywords.to_s,
        "promotional_text" => localization.promotional_text.to_s,
        "release_notes" => localization.whats_new.to_s,
        "support_url" => localization.support_url.to_s,
        "marketing_url" => localization.marketing_url.to_s
      )
      sets = snapshot_call("screenshot sets #{locale}", deadline) do
        localization.get_app_screenshot_sets(limit: SNAPSHOT_PAGE_LIMIT)
      end
      # An existing empty set is an empty list; a set that does not exist has no key.
      images[locale] = {}
      snapshot_page("screenshot sets #{locale}", sets).each do |set|
        display = set.screenshot_display_type
        raise snapshot_error("duplicate screenshot set #{locale}/#{display}") if images[locale].key?(display)

        images[locale][display] = Array(set.app_screenshots).map { |shot| snapshot_image(shot) }
      end
    end

    record = {
      "schema_version" => 1,
      "type" => "metadata-snapshot",
      "target" => identity,
      "version_id" => version.id,
      "editable" => SNAPSHOT_EDITABLE_STATES.include?(state),
      "review_active" => !submission.nil? || SNAPSHOT_REVIEW_STATES.include?(state),
      "app_info_id" => app_info&.id,
      "fields" => fields,
      "images" => images
    }
    record["binary"] = snapshot_binary(identity, build) if build
    record
  end

  # Only fields with a defined live equivalent; App Store Connect reports no SHA-256.
  def self.snapshot_image(shot)
    entry = { "id" => shot.id }
    delivery = shot.asset_delivery_state || {}
    entry["processing_state"] = delivery["state"] if delivery["state"].is_a?(String)
    asset = shot.image_asset || {}
    %w[width height].each do |key|
      entry[key] = asset[key] if asset[key].is_a?(Integer) && asset[key].positive?
    end
    entry
  end

  def self.snapshot_binary(identity, build)
    number = build.version
    unless number == identity["version"]["build"]
      raise snapshot_error("attached build #{number.inspect} differs from target build #{identity['version']['build']}")
    end
    unless build.processing_state.is_a?(String) && !build.processing_state.empty?
      raise snapshot_error("attached build #{number} has no processing state")
    end

    {
      "app_id" => identity["app_id"],
      "platform" => identity["platform"],
      "version" => identity["version"],
      "processing_state" => build.processing_state
    }
  end

  # The Python validators are authoritative; a record they reject is never written.
  # -B keeps bytecode caches out of the runtime checkout.
  def self.snapshot_validate(data)
    command = [ENV.fetch("PYTHON", "python3"), "-I", "-B", "-c", SNAPSHOT_VALIDATOR, snapshot_checkout]
    _, errors, result = Open3.capture3(*command, stdin_data: data)
    return if result.success?

    raise snapshot_error("record fails the public metadata validators: #{errors.strip.lines.last.to_s.strip}")
  end

  def self.snapshot_publish(output, data)
    temporary = File.join(File.dirname(output), ".#{File.basename(output)}.#{SecureRandom.hex(8)}.tmp")
    created = false
    begin
      File.open(temporary, File::WRONLY | File::CREAT | File::EXCL, 0o644) do |file|
        created = true
        file.write(data)
        file.flush
        file.fsync
      end
      # A hard link publishes the complete file atomically and, unlike rename, never replaces one.
      begin
        File.link(temporary, output)
      rescue Errno::EEXIST
        raise snapshot_error("output already exists: #{output}")
      rescue SystemCallError => error
        raise snapshot_error("could not publish #{output} with a hard link: #{error.class.name.split('::').last}")
      end
    ensure
      File.unlink(temporary) if created
    end
  end
end
