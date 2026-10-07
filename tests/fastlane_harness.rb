# Runs the actual lane, replacing only actions that access external systems.
require "json"

module UI
  def self.user_error!(message)
    raise message
  end
  def self.important(_message); end
end

class LaneHarness
  attr_reader :uploads, :review_reads
  def initialize(file)
    @lanes = {}
    @uploads = []
    @review_reads = 0
    instance_eval(File.read(file), file)
  end
  def default_platform(*); end
  def opt_out_usage; end
  def skip_docs; end
  def desc(*); end
  def platform(name)
    previous = @platform
    @platform = name
    yield
    @platform = previous
  end
  def lane(name, &block)
    @lanes[[@platform, name]] = block
  end
  def upload_to_app_store(**options)
    @uploads << options
  end
  alias deliver upload_to_app_store
  def run(options)
    # Replace account login/review lookup with an observed external boundary.
    define_singleton_method(:active_review_submission) do |**_|
      @review_reads += 1
      nil
    end
    define_singleton_method(:app_store_connect_key) { { key_id: "fixture" } }
    instance_exec(options, &@lanes.fetch([:ios, :metadata]))
  end
end

harness = LaneHarness.new(ARGV.fetch(0))
begin
  harness.run(JSON.parse(ARGV.fetch(1), symbolize_names: true))
  puts JSON.generate(uploads: harness.uploads, review_reads: harness.review_reads)
rescue StandardError => error
  warn error.message
  puts JSON.generate(uploads: harness.uploads, review_reads: harness.review_reads)
  exit 1
end
