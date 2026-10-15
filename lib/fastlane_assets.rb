require "json"
require "open3"
require "digest"
require "securerandom"
require "timeout"
require "tmpdir"
require "fileutils"

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
  SNAPSHOT_TARGET_VALIDATOR = <<~PYTHON.freeze
    import json, sys
    sys.path.insert(0, sys.argv[1])
    from app_store_assets.contracts import target_identity
    target_identity(json.loads(sys.stdin.read()))
  PYTHON

  # Reads the App Store Connect state of one Apple iOS target and writes one
  # metadata-snapshot record. Call it only after the lane has authenticated Spaceship.
  # It makes no remote write and never replaces an existing file.
  def self.export_snapshot(target:, output:, deadline: SNAPSHOT_DEFAULT_DEADLINE)
    identity = snapshot_target(target)
    # The same identity validation that the record faces at the end, before any provider read.
    snapshot_python(SNAPSHOT_TARGET_VALIDATOR, JSON.generate(identity), "target fails the identity validator")
    unless deadline.is_a?(Numeric) && deadline.positive? && deadline <= SNAPSHOT_MAX_DEADLINE
      raise snapshot_error("deadline must be more than 0 and at most #{SNAPSHOT_MAX_DEADLINE} seconds")
    end

    output, directory = snapshot_output(output)
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
    snapshot_publish(output, directory, data)
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

  class TransferRefusal < StandardError; end
  TRANSFER_JSON_LIMIT = 8 * 1024 * 1024
  TRANSFER_VERIFIER = <<~PYTHON.freeze
    import runpy, sys
    sys.path.insert(0, sys.argv.pop(1))
    runpy.run_module("app_store_assets_local.transfer", run_name="__main__")
  PYTHON

  # U3 only: verifies authority and live state; no upload, delete, or reorder.
  def self.transfer_screenshots(root:, target:, plan:, approval:, mode: "read-only",
                               deadline: SNAPSHOT_DEFAULT_DEADLINE,
                               verification_deadline: SNAPSHOT_DEFAULT_DEADLINE)
    raise transfer_error("only read-only mode is available") unless mode.to_s.tr("_", "-") == "read-only"
    [deadline, verification_deadline].each do |limit|
      unless limit.is_a?(Numeric) && limit.positive? && limit <= SNAPSHOT_MAX_DEADLINE
        raise transfer_error("deadline must be more than 0 and at most #{SNAPSHOT_MAX_DEADLINE} seconds")
      end
    end
    begin
      identity = snapshot_target(target)
    rescue StandardError
      raise transfer_error("invalid target")
    end

    result = nil
    transfer_lock(identity) do |check_lock|
      transfer_staging do |directory|
        command = ["-I", "-B", "-c", TRANSFER_VERIFIER, snapshot_checkout,
                   "--root", root, "--plan", plan, "--approval", approval,
                   "--staging-dir", File.realpath(directory)]
        intent = JSON.parse(transfer_python(command, "", verification_deadline))
        unless intent["type"] == "verified-transfer-intent" && intent["target"] == identity && intent["operation"] == "images"
          raise transfer_error("verified intent target or operation differs")
        end
        check_lock.call
        labels = intent.fetch("groups").map { |group| "#{group.fetch('locale')}/#{group.fetch('slot')}" }.join(", ")
        labels = "target" if labels.empty?
        live = transfer_provider_output do
          transfer_call("load Spaceship", deadline) { require "spaceship" }
          begin
            snapshot_record(identity, deadline, reader: lambda { |label, limit, &operation|
              transfer_call("#{labels}: #{label}", limit, &operation)
            })
          rescue TransferRefusal
            raise
          rescue StandardError
            raise transfer_error("#{labels}: live snapshot could not be read")
          end
        end
        transfer_python(["-I", "-B", "-c", SNAPSHOT_VALIDATOR, snapshot_checkout], JSON.generate(live), verification_deadline)
        result = transfer_compare(intent, live, labels)
        check_lock.call
      end
    end
    output = JSON.generate(result) + "\n"
    raise transfer_error("result exceeds JSON byte bound") if output.bytesize > TRANSFER_JSON_LIMIT

    $stdout.write(output)
    $stdout.flush
    result
  rescue TransferRefusal
    raise
  rescue StandardError
    raise transfer_error("local verification or cleanup failed")
  end

  def self.transfer_error(message)
    TransferRefusal.new("App Store screenshot transfer refused: #{message}")
  end

  def self.transfer_lock(identity)
    # A fixed machine-wide path prevents TMPDIR or project changes from splitting the lock.
    name = "app-store-assets-transfer-#{Digest::SHA256.hexdigest(identity.fetch('app_id'))}.lock"
    path = File.join(File.realpath("/tmp"), name)
    begin
      lock = File.open(path, File::WRONLY | File::CREAT | File::EXCL | File::NOFOLLOW, 0o600)
    rescue Errno::EEXIST
      raise transfer_error("target lock exists; only the operator may remove an existing lock")
    end
    owned = lock.stat
    same_lock = lambda do
      observed = File.lstat(path)
      observed.file? && [observed.dev, observed.ino] == [owned.dev, owned.ino]
    rescue Errno::ENOENT
      false
    end
    begin
      lock.write("#{Process.pid}\n")
      lock.flush
      yield lambda { raise transfer_error("target lock changed") unless same_lock.call }
    ensure
      lock.close
      transfer_remove_owned(path, owned, "target lock")
    end
  end

  def self.transfer_staging
    directory = File.realpath(Dir.mktmpdir("app-store-assets-transfer-"))
    owned = File.lstat(directory)
    begin
      yield directory
    ensure
      transfer_remove_owned(directory, owned, "staging directory")
    end
  end

  # Isolate the entry before deletion, then check what the rename actually moved.
  # A raced replacement is retained for operator recovery, never restored over a new lock.
  def self.transfer_remove_owned(path, owned, label)
    same_entry = lambda do |candidate|
      observed = File.lstat(candidate)
      [observed.dev, observed.ino, observed.ftype] == [owned.dev, owned.ino, owned.ftype]
    rescue Errno::ENOENT
      false
    end
    raise transfer_error("#{label} changed; retained at #{path}") unless same_entry.call(path)

    quarantine = Dir.mktmpdir(".app-store-assets-cleanup-", File.dirname(path))
    captured = File.join(quarantine, "entry")
    File.rename(path, captured)
    unless same_entry.call(captured)
      raise transfer_error("#{label} changed during cleanup; retained at #{captured}")
    end
    FileUtils.remove_entry(captured)
  ensure
    if quarantine
      begin
        Dir.rmdir(quarantine)
      rescue Errno::ENOTEMPTY
        nil
      end
    end
  end

  # No block form of popen3: its implicit wait can outlive a Timeout exception.
  # Drain both pipes and feed stdin under one deadline, then reap or kill the process group.
  def self.transfer_python(arguments, input, deadline)
    raise transfer_error("verification input exceeds JSON byte bound") if input.bytesize > TRANSFER_JSON_LIMIT

    input = input.b
    stdin, stdout, stderr, process = Open3.popen3(ENV.fetch("PYTHON", "python3"), *arguments, pgroup: true)
    expires = Process.clock_gettime(Process::CLOCK_MONOTONIC) + deadline
    buffers = { stdout => +"".b, stderr => +"".b }
    readers = buffers.keys
    offset = 0
    stdin.close if input.empty?
    until readers.empty? && stdin.closed?
      remaining = expires - Process.clock_gettime(Process::CLOCK_MONOTONIC)
      raise transfer_error("local verification exceeded its deadline") unless remaining.positive?

      ready = IO.select(readers, stdin.closed? ? [] : [stdin], nil, remaining)
      raise transfer_error("local verification exceeded its deadline") if ready.nil?

      ready[0].each do |stream|
        chunk = stream.read_nonblock(65_536, exception: false)
        if chunk.nil?
          readers.delete(stream)
          stream.close
        elsif chunk != :wait_readable
          buffers[stream] << chunk
          raise transfer_error("verification output exceeds JSON byte bound") if buffers[stream].bytesize > TRANSFER_JSON_LIMIT
        end
      end
      ready[1].each do |stream|
        written = stream.write_nonblock(input.byteslice(offset, 65_536), exception: false)
        next if written == :wait_writable

        offset += written
        stream.close if offset == input.bytesize
      end
    end
    remaining = expires - Process.clock_gettime(Process::CLOCK_MONOTONIC)
    unless remaining.positive? && process.join(remaining)
      raise transfer_error("local verification exceeded its deadline")
    end
    raise transfer_error("local verification refused") unless process.value.success?

    buffers.fetch(stdout)
  ensure
    [stdin, stdout, stderr].compact.each { |stream| stream.close unless stream.closed? }
    # A reaped parent can leave descendants holding the pipes open.
    if process
      begin
        Process.kill("KILL", -process.pid)
      rescue Errno::ESRCH
        nil
      end
      process.join(1)
    end
  end

  def self.transfer_provider_output
    original_stdout = $stdout
    saved_stdout = STDOUT.dup
    begin
      STDOUT.flush
      STDOUT.reopen(STDERR)
      $stdout = $stderr
      yield
    ensure
      STDOUT.flush
      STDOUT.reopen(saved_stdout)
      saved_stdout.close
      $stdout = original_stdout
    end
  end

  def self.transfer_call(label, deadline, &operation)
    Timeout.timeout(deadline, &operation)
  rescue Timeout::Error
    raise transfer_error("provider call exceeded its deadline: #{label}")
  rescue LoadError
    raise transfer_error("Spaceship is unavailable; use an authenticated Fastlane lane")
  rescue StandardError
    raise transfer_error("provider call failed: #{label}")
  end

  def self.transfer_compare(intent, live, labels)
    supplied = intent.fetch("remote")
    unless supplied["version_id"].is_a?(String) && !supplied["version_id"].empty? &&
           supplied["editable"] == true && supplied["review_active"] == false &&
           live["editable"] == true && live["review_active"] == false && live["binary"]
      raise transfer_error("#{labels}: version, review state or approved attached build is not ready")
    end
    mapped = live.merge("build_exists" => !live["binary"].nil?, "release_notes" => live.fetch("fields").to_h { |locale, fields| [locale, fields["release_notes"]] })
    transfer_match(supplied.reject { |key, _| key == "images" }, mapped, "snapshot", labels)
    declared = intent.fetch("groups")
    groups = declared.map do |group|
      locale, slot = group.fetch("locale"), group.fetch("slot")
      label = "#{locale}/#{slot}"
      expected = supplied.fetch("images", {}).fetch(locale, {})
      observed = live.fetch("images").fetch(locale, {})
      unless expected.key?(slot) == observed.key?(slot)
        raise transfer_error("#{label}: screenshot set presence differs from the snapshot")
      end
      if expected.key?(slot)
        unless expected.fetch(slot).all? { |image| image["id"].is_a?(String) && !image["id"].empty? }
          raise transfer_error("#{label}: snapshot screenshot IDs are required")
        end
        transfer_match(expected.fetch(slot), observed.fetch(slot), "images", label)
      end
      images = observed.fetch(slot, [])
      {
        locale: locale, slot: slot, action: "verify",
        readback: { snapshot_matches: true, screenshot_count: images.size },
        remote_screenshot_ids: images.map { |image| image.fetch("id") }
      }
    end
    preserved = declared.map { |group| group.fetch("locale") }.uniq.to_h do |locale|
      slots = declared.select { |group| group["locale"] == locale }.map { |group| group.fetch("slot") }
      [locale, live.fetch("images").fetch(locale, {}).reject { |slot, _| slots.include?(slot) }]
    end
    {
      plan_digest: intent.fetch("plan_digest"), target: intent.fetch("target"), mode: "read-only",
      remote_verified: true, provenance: intent.fetch("provenance"), groups: groups, preserved_sets: preserved
    }
  end

  # Compare every supplied observation; absent live keys are not silently skipped.
  def self.transfer_match(expected, observed, path, label)
    if expected.is_a?(Hash) && observed.is_a?(Hash)
      expected.each do |key, value|
        raise transfer_error("#{label}: no live mapping for #{path}.#{key}") unless observed.key?(key)

        transfer_match(value, observed.fetch(key), "#{path}.#{key}", label)
      end
    elsif expected.is_a?(Array) && observed.is_a?(Array) && expected.size == observed.size
      expected.zip(observed).each_with_index { |(left, right), index| transfer_match(left, right, "#{path}[#{index}]", label) }
    elsif expected != observed
      raise transfer_error("#{label}: snapshot differs at #{path}")
    end
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

    # The directory's identity binds publication to the directory validated here.
    stat = File.stat(parent)
    [File.join(parent, File.basename(output)), [stat.dev, stat.ino]]
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

  def self.snapshot_record(identity, deadline, reader: method(:snapshot_call))
    api = Spaceship::ConnectAPI
    bundle_id = identity["app_id"]
    name = identity["version"]["name"]

    app = reader.call("app", deadline) { api::App.find(bundle_id) }
    raise snapshot_error("no App Store Connect app for #{bundle_id}") if app.nil?

    versions = reader.call("app store versions", deadline) do
      app.get_app_store_versions(filter: { versionString: name, platform: "IOS" })
    end
    matches = Array(versions).select { |item| item.version_string == name && item.platform == "IOS" }
    raise snapshot_error("no iOS App Store version #{name} for #{bundle_id}") if matches.empty?
    raise snapshot_error("more than one iOS App Store version #{name} for #{bundle_id}") if matches.size > 1

    version = matches.first
    raise snapshot_error("App Store version #{name} has no ID") unless version.id.is_a?(String) && !version.id.empty?

    state = version.app_version_state || version.app_store_state
    submission = reader.call("review submission", deadline) do
      app.get_in_progress_review_submission(platform: "IOS")
    end
    build = reader.call("attached build", deadline) { snapshot_attached_build(version) }
    app_info = reader.call("app info", deadline) { app.fetch_edit_app_info }
    # fetch_edit_app_info also returns an app info in WAITING_FOR_REVIEW, which accepts no edit.
    app_info = nil unless app_info.nil? || SNAPSHOT_APP_INFO_EDITABLE_STATES.include?(app_info.state)

    fields = {}
    if app_info
      infos = reader.call("app info localizations", deadline) do
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
    localizations = reader.call("version localizations", deadline) do
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
      sets = reader.call("screenshot sets #{locale}", deadline) do
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

  # The build attached to the version, or nil when none is. For a version without a
  # build, App Store Connect answers with `"data": null`, and Spaceship 2.240.1's
  # Models.parse raises exactly "No data" for it instead of returning nothing.
  def self.snapshot_attached_build(version)
    version.get_build
  rescue RuntimeError => error
    raise unless error.message == "No data"

    nil
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
  def self.snapshot_validate(data)
    snapshot_python(SNAPSHOT_VALIDATOR, data, "record fails the public metadata validators")
  end

  # Runs a validator from this checkout; -B keeps bytecode caches out of it.
  def self.snapshot_python(script, data, message)
    command = [ENV.fetch("PYTHON", "python3"), "-I", "-B", "-c", script, snapshot_checkout]
    _, errors, result = Open3.capture3(*command, stdin_data: data)
    return if result.success?

    raise snapshot_error("#{message}: #{errors.strip.lines.last.to_s.strip}")
  end

  # Publishes inside the directory that snapshot_output validated, even when its path was
  # replaced during the provider read: after the chdir, the identity check binds the working
  # directory to that directory, and every relative name below resolves inside it.
  # The exporter runs single-threaded in a lane, so the block's working directory is safe to use.
  def self.snapshot_publish(output, directory, data)
    name = File.basename(output)
    # An opaque name, so a long output name cannot exceed the file-name limit here.
    temporary = ".snapshot-#{SecureRandom.hex(16)}.tmp"
    begin
      Dir.chdir(File.dirname(output)) do
        stat = File.stat(".")
        unless [stat.dev, stat.ino] == directory
          raise snapshot_error("output directory changed during the export: #{File.dirname(output)}")
        end

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
            File.link(temporary, name)
          rescue Errno::EEXIST
            raise snapshot_error("output already exists: #{output}")
          rescue SystemCallError => error
            raise snapshot_error("could not publish #{output} with a hard link: #{error.class.name.split('::').last}")
          end
        ensure
          File.unlink(temporary) if created
        end
      end
    rescue SystemCallError => error
      raise snapshot_error("could not publish #{output}: #{error.class.name.split('::').last}")
    end
  end
end
