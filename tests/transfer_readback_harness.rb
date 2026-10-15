# Calls the read-only transfer entrypoint without a real gem or store connection.
require ARGV.fetch(0)
require "spaceship" if ENV["FAKE_ASC_PRELOAD"]

if ENV["FAKE_TRANSFER_SWAP_STAGE"]
  AppStoreAssets.singleton_class.prepend(Module.new do
    def transfer_python(arguments, *rest)
      result = super
      index = arguments.index("--staging-dir")
      if index
        directory = arguments.fetch(index + 1)
        File.rename(directory, directory + ".owned")
        Dir.mkdir(directory, 0o700)
        File.write(File.join(directory, "marker"), "foreign staging content")
        File.write(ENV.fetch("FAKE_TRANSFER_SWAP_STAGE"), JSON.generate(directory: directory))
        raise transfer_error("injected verifier failure")
      end
      result
    end
  end)
end

if ENV["FAKE_TRANSFER_SWAP_LOCK"]
  AppStoreAssets.singleton_class.prepend(Module.new do
    def transfer_compare(*)
      result = super
      $transfer_finished = true
      result
    end
  end)
  File.singleton_class.prepend(Module.new do
    def lstat(path)
      observed = super
      if $transfer_finished && File.basename(path).start_with?("app-store-assets-transfer-") && path.end_with?(".lock")
        @cleanup_checks = (@cleanup_checks || 0) + 1
        if @cleanup_checks == 2
          $transfer_finished = false
          log = ENV.fetch("FAKE_TRANSFER_SWAP_LOCK")
          File.rename(path, log + ".owned")
          File.write(path, "foreign lock content")
          File.write(log, JSON.generate(original: path, retained: path))
        end
      end
      observed
    end

    def rename(source, destination)
      result = super
      log = ENV.fetch("FAKE_TRANSFER_SWAP_LOCK")
      if File.exist?(log)
        record = JSON.parse(File.read(log))
        if source == record["original"]
          record["retained"] = destination
          File.write(log, JSON.generate(record))
        end
      end
      result
    end
  end)
end

options = JSON.parse(ARGV.fetch(3), symbolize_names: true)
begin
  AppStoreAssets.transfer_screenshots(
    root: ARGV.fetch(1), target: JSON.parse(ARGV.fetch(2), symbolize_names: true),
    plan: "plan.json", approval: "approval.json", **options
  )
rescue StandardError => error
  warn "ERROR: #{error.message}"
  exit 1
end
