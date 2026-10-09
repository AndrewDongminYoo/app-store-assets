"""Ruby child loader for captured sources and Bundler's reviewed inputs."""

BOOTSTRAP = r'''
require "json"
require "stringio"
capture = IO.new(Integer(ARGV.shift), "r")
length = capture.pread(8, 0).unpack1("Q>")
bundle = JSON.parse(capture.pread(length, 8))
CAPTURED_ARCHIVE = capture
CAPTURED_FILES = bundle.fetch("files").freeze
CAPTURED_ROOTS = bundle.fetch("roots").freeze
CAPTURED_NAMES = CAPTURED_FILES.keys.freeze
CAPTURED_ENTRY = bundle.fetch("entry")
CAPTURED_DIRECTORIES = bundle.fetch("directories")
initial = File.stat(".")
CAPTURED_DIRECTORIES["#{initial.dev}:#{initial.ino}"] ||= Dir.pwd
module CapturedWorkingDirectory
  def pwd
    info = File.stat(".")
    CAPTURED_DIRECTORIES.fetch("#{info.dev}:#{info.ino}") { super }
  end
  alias getwd pwd
end
Dir.singleton_class.prepend(CapturedWorkingDirectory)

module CapturedProvider
  def self.path(path)
    File.expand_path(path.to_s, Dir.pwd)
  end
  def self.staged?(path)
    return false unless path.is_a?(String) || path.respond_to?(:to_path)
    path = self.path(path)
    CAPTURED_ROOTS.any? { |root| path == root || path.start_with?(root + "/") }
  end
  def self.read(path)
    item = CAPTURED_FILES.fetch(self.path(path)) { raise LoadError, "uncaptured staged provider code" }
    CAPTURED_ARCHIVE.pread(item.fetch("size"), item.fetch("offset"))
  end
  def self.candidate(feature, cwd_fallback=false)
    explicit = feature.start_with?("/", "./", "../")
    paths = explicit ? [self.path(feature)] : $LOAD_PATH.map { |root| self.path(File.join(root, feature)) }
    paths << self.path(feature) if cwd_fallback && !explicit
    staged_search = false
    paths.each do |path|
      names = cwd_fallback ? [path] : [path, path + ".rb", path + ".so", path + ".bundle"]
      names.each do |name|
        return {path:name, captured:true} if CAPTURED_FILES.key?(name)
        if staged?(name)
          staged_search = true
          next
        end
        return {path:name, captured:false} if File.file?(name)
      end
    end
    raise LoadError, "uncaptured staged provider code" if staged_search
    # Only installed-library activation may retain an unresolved feature name.
    {path:feature, captured:false}
  end
end

module CapturedRequires
  def require(feature)
    selected = CapturedProvider.candidate(feature)
    return super(selected.fetch(:path)) unless selected.fetch(:captured)
    path = selected.fetch(:path)
    return false if $LOADED_FEATURES.include?(path)
    $LOADED_FEATURES << path
    begin
      eval(CapturedProvider.read(path).force_encoding("UTF-8"), TOPLEVEL_BINDING, path)
    rescue Exception
      $LOADED_FEATURES.delete(path)
      raise
    end
    true
  end
  def require_relative(feature)
    caller = caller_locations(1, 1).first
    origin = caller.absolute_path || caller.path
    Kernel.require(File.expand_path(feature, File.dirname(origin)))
  end
  def load(feature, wrap=false)
    selected = CapturedProvider.candidate(feature, true)
    return super(selected.fetch(:path), wrap) unless selected.fetch(:captured)
    path = selected.fetch(:path)
    raise LoadError, "wrapped staged loads are unsupported" if wrap
    eval(CapturedProvider.read(path).force_encoding("UTF-8"), TOPLEVEL_BINDING, path)
    true
  end
end
Object.prepend(CapturedRequires)
Kernel.singleton_class.prepend(CapturedRequires)

module CapturedFileReads
  def new(path, mode="r", *args, **options)
    return super unless CapturedProvider.staged?(path)
    open(path, mode, *args, **options)
  end
  def sysopen(path, *args)
    raise IOError, "raw staged descriptors are unsupported; use captured file reads" if CapturedProvider.staged?(path)
    super
  end
  def read(path, length=nil, offset=0, **options)
    return super unless CapturedProvider.staged?(path)
    value = CapturedProvider.read(path)
    value = value.byteslice(offset, length || value.bytesize) || ""
    value.force_encoding(options[:encoding] || "UTF-8")
  end
  def binread(path, length=nil, offset=0)
    return super unless CapturedProvider.staged?(path)
    CapturedProvider.read(path).byteslice(offset, length || CAPTURED_FILES.fetch(CapturedProvider.path(path)).fetch("size")) || ""
  end
  def open(path, mode="r", *args, **options)
    return super unless CapturedProvider.staged?(path)
    raise IOError, "captured provider files are read-only" unless mode.is_a?(String) && mode.match?(/\Arb?(?::.*)?\z/)
    stream = StringIO.new(CapturedProvider.read(path), "r")
    return stream unless block_given?
    begin
      yield stream
    ensure
      stream.close
    end
  end
  def readlines(path, *args, **options)
    return super unless CapturedProvider.staged?(path)
    open(path) { |file| file.readlines(*args, **options) }
  end
  def foreach(path, *args, **options, &block)
    return super unless CapturedProvider.staged?(path)
    return enum_for(:foreach, path, *args, **options) unless block
    open(path) { |file| file.each_line(*args, **options, &block) }
  end
end
File.singleton_class.prepend(CapturedFileReads)
IO.singleton_class.prepend(CapturedFileReads)

# Bundler must consume the capture before any -r startup feature is loaded.
# Disable local .bundle/config; it can introduce new code/search paths.
ENV["BUNDLE_IGNORE_CONFIG"] = "true"
if bundle["gemfile"]
  require "bundler"
  module CapturedBundlerReads
    def read_file(path)
      return CapturedProvider.read(path).dup.force_encoding("UTF-8") if CapturedProvider.staged?(path)
      super
    end
  end
  Bundler.singleton_class.prepend(CapturedBundlerReads)
  module CapturedFilePresence
    def file?(path)
      return CAPTURED_NAMES.include?(CapturedProvider.path(path)) if CapturedProvider.staged?(path)
      super
    end
    def exist?(path)
      return true if CapturedProvider.staged?(path) && CAPTURED_NAMES.include?(CapturedProvider.path(path))
      super
    end
  end
  File.singleton_class.prepend(CapturedFilePresence)
end
bundle.fetch("requires").each { |feature| require feature }
$0 = CAPTURED_ENTRY
eval(CapturedProvider.read(CAPTURED_ENTRY).force_encoding("UTF-8"), TOPLEVEL_BINDING, CAPTURED_ENTRY)
'''
