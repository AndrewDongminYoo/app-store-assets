require "json"
require "open3"

module AppStoreAssets
  # Protocol v1. No account login or remote mutation is performed here.
  def self.prepare(repo_root:, project:, bundle_id:, source:, subdir: ".", normalize_alpha: false)
    command = [ENV.fetch("PYTHON", "python3"), File.expand_path("../assets.py", __dir__),
               "prepare-screenshots", "--source", source,
               "--out", File.join(repo_root, "build/store-assets/ios-bundles"),
               "--project", project, "--bundle-id", bundle_id, "--subdir", subdir]
    command << "--normalize-alpha" if normalize_alpha
    output, errors, result = Open3.capture3(*command)
    raise "App Store screenshot preparation failed: #{errors.strip}" unless result.success?

    bundle = JSON.parse(output)
    { screenshots_path: bundle.fetch("screenshots_path"), overwrite_screenshots: true }
  end
end
