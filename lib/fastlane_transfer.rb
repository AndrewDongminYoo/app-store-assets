# Loaded by fastlane_assets.rb. Provider loading remains inside the entrypoint.
module AppStoreAssets
  def self.transfer_execute(intent, live, context, directory, changed, check_lock,
                            deadline, group_deadline, poll_interval, request_timeout)
    groups = intent.fetch("groups")
    groups.each { |group| transfer_check_files(group, directory) }
    baseline = transfer_preserved(context, groups)
    actions = groups.map do |group|
      locale, slot = group.values_at("locale", "slot")
      label = "#{locale}/#{slot}"
      localization = context.fetch(:localizations)[locale]
      raise transfer_error("#{label}: version localization is missing") unless localization

      set = context.fetch(:sets).fetch(locale).fetch(slot, nil)
      shots = set ? Array(set.app_screenshots) : []
      planned = group.fetch("images").map { |image| image.fetch("md5") }
      action = if shots.map(&:source_file_checksum) == planned
                 "unchanged"
               elsif shots.empty?
                 "upload"
               elsif intent.fetch("replacement").fetch("allow_delete")
                 "replace"
               else
                 raise transfer_error("#{label}: different non-empty group requires allow_delete")
               end
      { group: group, label: label, localization: localization, set: set, action: action,
        original_ids: shots.map(&:id) }
    end

    variables = %w[SPACESHIP_TIMEOUT SPACESHIP_SCREENSHOT_UPLOAD_TIMEOUT]
    previous = variables.to_h { |key| [key, ENV[key]] }
    begin
      ENV["SPACESHIP_TIMEOUT"] = [request_timeout.ceil, 1].max.to_s
      ENV["SPACESHIP_SCREENSHOT_UPLOAD_TIMEOUT"] = [(group_deadline / 60.0).ceil, 1].max.to_s
      actions.select { |item| item[:action] == "unchanged" }.each do |item|
        item[:readback] = transfer_poll(item, deadline, group_deadline, poll_interval, false, changed, check_lock)
        unless item[:readback].map { |shot| shot.fetch("id") } == item[:original_ids]
          raise transfer_error("#{item[:label]}: unchanged group IDs changed during preflight")
        end
      end
      # An unchanged group's poll can take minutes. Check all staged bytes again before writing.
      groups.each { |group| transfer_check_files(group, directory) }
      check_lock.call
      actions.reject { |item| item[:action] == "unchanged" }.each do |item|
        expires = transfer_now + group_deadline
        write = lambda do |label, &operation|
          check_lock.call
          changed << item[:label] unless changed.include?(item[:label])
          transfer_call("#{item[:label]}: #{label}", transfer_remaining(expires, deadline, item[:label]), &operation)
        end
        unless item[:set]
          item[:set] = write.call("create screenshot set") do
            item[:localization].create_app_screenshot_set(attributes: { screenshotDisplayType: item[:group].fetch("slot") })
          end
        end
        set = item[:set]
        raise transfer_error("#{item[:label]}: created set has no ID") unless set && set.id.is_a?(String) && !set.id.empty?

        if item[:action] == "replace"
          Array(set.app_screenshots).each { |shot| write.call("delete screenshot") { shot.delete! } }
        end
        item[:group].fetch("images").each_with_index do |image, position|
          transfer_check_file(image, directory, item[:label])
          write.call("upload screenshot #{position}") do
            set.upload_screenshot(path: image.fetch("staged_path"), wait_for_processing: false, position: position)
          end
        end
        item[:readback] = transfer_poll(item, deadline, group_deadline, poll_interval, true, changed, check_lock, expires)
      end

      final_context = {}
      final = snapshot_record(intent.fetch("target"), deadline, context: final_context,
                              reader: lambda { |label, limit, &operation| transfer_call("final read: #{label}", limit, &operation) })
      # Reuse every supplied non-image mapping, now against the initial live read as well.
      transfer_compare(intent.merge("groups" => [], "remote" => live.reject { |key, _| key == "images" }), final, "final read")
      unless final_context.values_at(:version_state, :build_id) == context.values_at(:version_state, :build_id)
        raise transfer_error("final read: version state or attached build changed")
      end
      unless transfer_preserved(final_context, groups) == baseline
        raise transfer_error("final read: preserved screenshot sets changed")
      end
      actions.each do |item|
        set = final_context.fetch(:sets).fetch(item[:group].fetch("locale"), {})[item[:group].fetch("slot")]
        unless set && set.id == item[:set]&.id && transfer_shots(set) == item[:readback]
          raise transfer_error("#{item[:label]}: final read differs from group readback")
        end
      end
      check_lock.call
      {
        plan_digest: intent.fetch("plan_digest"), target: intent.fetch("target"), mode: "transfer",
        remote_verified: true, provenance: intent.fetch("provenance"),
        groups: actions.map do |item|
          { locale: item[:group].fetch("locale"), slot: item[:group].fetch("slot"), action: item[:action],
            readback: { complete: true, checksums_match: true, screenshot_count: item[:readback].size },
            remote_screenshot_ids: item[:readback].map { |shot| shot.fetch("id") } }
        end
      }
    ensure
      previous.each { |key, value| value.nil? ? ENV.delete(key) : ENV[key] = value }
    end
  end

  def self.transfer_check_files(group, directory)
    group.fetch("images").each { |image| transfer_check_file(image, directory, "#{group.fetch('locale')}/#{group.fetch('slot')}") }
  end

  def self.transfer_check_file(image, directory, label)
    path = image.fetch("staged_path")
    unless File.dirname(path) == directory && File.realpath(directory) == directory
      raise transfer_error("#{label}: staged path escaped its private directory")
    end
    File.open(path, File::RDONLY | File::NOFOLLOW) do |file|
      stat = file.stat
      unless stat.file? && stat.nlink == 1 && (stat.mode & 0o077).zero?
        raise transfer_error("#{label}: staged file is not private and regular")
      end
      sha256, md5 = Digest::SHA256.new, Digest::MD5.new
      while (bytes = file.read(1024 * 1024))
        sha256.update(bytes)
        md5.update(bytes)
      end
      unless sha256.hexdigest == image.fetch("sha256") && md5.hexdigest == image.fetch("md5")
        raise transfer_error("#{label}: staged checksum differs from verified bytes")
      end
    end
  rescue SystemCallError
    raise transfer_error("#{label}: staged file is unavailable")
  end

  def self.transfer_shots(set)
    Array(set.app_screenshots).map do |shot|
      snapshot_image(shot).merge("md5" => shot.source_file_checksum)
    end
  end

  def self.transfer_preserved(context, groups)
    groups.map { |group| group.fetch("locale") }.uniq.to_h do |locale|
      slots = groups.select { |g| g["locale"] == locale }.map { |g| g.fetch("slot") }
      sets = context.fetch(:sets).fetch(locale, {}).reject { |slot, _| slots.include?(slot) }
      [locale, sets.to_h { |slot, set| [slot, { "id" => set.id, "images" => transfer_shots(set) }] }]
    end
  end

  def self.transfer_now
    Process.clock_gettime(Process::CLOCK_MONOTONIC)
  end

  def self.transfer_remaining(expires, deadline, label)
    remaining = expires - transfer_now
    raise transfer_error("#{label}: group deadline exceeded") unless remaining.positive?

    [remaining, deadline].min
  end

  def self.transfer_poll(item, deadline, group_deadline, interval, can_reorder, changed, check_lock, expires = nil)
    expires ||= transfer_now + group_deadline
    planned = item[:group].fetch("images").map { |image| image.fetch("md5") }
    reordered = false
    loop do
      check_lock.call
      limit = transfer_remaining(expires, deadline, item[:label])
      set = transfer_call("#{item[:label]}: processing read", limit) do
        Spaceship::ConnectAPI::AppScreenshotSet.get(app_screenshot_set_id: item[:set].id)
      end
      unless set && set.id == item[:set].id && set.screenshot_display_type == item[:group].fetch("slot")
        raise transfer_error("#{item[:label]}: screenshot set changed during readback")
      end
      shots = transfer_shots(set)
      if shots.any? { |shot| shot["processing_state"] == "FAILED" }
        raise transfer_error("#{item[:label]}: screenshot processing failed")
      end
      if shots.size == planned.size && shots.all? { |shot| shot["processing_state"] == "COMPLETE" && !shot["md5"].to_s.empty? }
        ids = shots.map { |shot| shot["id"] }
        unless ids.all? { |id| id.is_a?(String) && !id.empty? } && ids.uniq.size == ids.size
          raise transfer_error("#{item[:label]}: readback screenshot IDs are invalid")
        end
        observed = shots.map { |shot| shot.fetch("md5") }
        return shots if observed == planned

        raise transfer_error("#{item[:label]}: readback checksum differs") unless observed.sort == planned.sort
        raise transfer_error("#{item[:label]}: readback order differs") unless can_reorder && !reordered

        available = shots.group_by { |shot| shot.fetch("md5") }
        ordered = planned.map { |md5| available.fetch(md5).shift.fetch("id") }
        check_lock.call
        changed << item[:label] unless changed.include?(item[:label])
        transfer_call("#{item[:label]}: reorder screenshots", transfer_remaining(expires, deadline, item[:label])) do
          set.reorder_screenshots(app_screenshot_ids: ordered)
        end
        reordered = true
        next
      end
      sleep [interval, transfer_remaining(expires, deadline, item[:label])].min
    end
  end
end
