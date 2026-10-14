# Calls AppStoreAssets.export_snapshot as a consumer lane would, with symbol keys.
# Run it with --disable-gems and -I tests/fake_spaceship so that no fastlane gem loads.
# Standard output is the method's own; a refusal goes to standard error.
require ARGV.fetch(0)
# Stands for a lane that loaded Spaceship, and built its logger, while it authenticated.
require "spaceship" if ENV["FAKE_ASC_PRELOAD"]

options = { target: JSON.parse(ARGV.fetch(1), symbolize_names: true), output: ARGV.fetch(2) }
options[:deadline] = Float(ARGV.fetch(3)) if ARGV.size > 3
begin
  AppStoreAssets.export_snapshot(**options)
rescue StandardError => error
  warn "ERROR: #{error.message}"
  exit 1
end
