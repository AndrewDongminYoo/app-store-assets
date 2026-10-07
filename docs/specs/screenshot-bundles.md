# Screenshot Bundles, Protocol 1

## Scope

Prepare existing personal App Store screenshots for the legacy Fastlane adapter.
Preserve native project capture, native composition, source bytes, previous bundles, and unrelated changes.
No store login, upload, publishing, review submission, device install, or simulator build is part of preparation.

## Input and Output

The source has locale folders containing PNG or JPEG images.
Mirae supplies `images/iphone65` as the subdirectory within each locale.
Reject an empty source, unsupported resolution, alpha channel, malformed pixel stream, or more than ten images per locale and legacy display class.
Reject hidden screenshot filenames because Fastlane skips them.
Allow only `.png`, `.PNG`, `.jpg`, `.JPG`, `.jpeg`, and `.JPEG`, and require the decoded image format to match the extension.
PNG alpha normalization is opt-in and requires every pixel to be opaque.
Do not invent a background for transparent artwork.
Exclude generated PNG date and time chunks; retain color metadata.
Reproducibility applies within the same ImageMagick runtime, not across encoder versions.

Create a separate content-addressed bundle with `manifest.json` and `screenshots/<locale>/<filename>`.
The manifest contains `schema_version: 1`, personal account scope, project, bundle identifier, replacement policy, and assets with original and final SHA-256, final dimensions, locale, kind, and display profile.
Existing imports have `provenance.status: unverified-import`.
Do not infer capture commit, installed build, or device from current checkout metadata.
Versioned capture evidence will be added in the next pilot stage.

Bundle validation reads the actual file bytes and decodes each image.
It compares hashes, dimensions, display profiles, and the entire screenshot inventory.
Partially prepared bundles must not become visible to uploaders.
Reuse validates the existing bundle and compares its parsed manifest with the manifest freshly computed from current inputs.
A modified image with a correspondingly modified cached manifest must fail reuse.
Publish by atomic directory rename; on an existing-destination race, validate and compare the winner before returning it.
Other filesystem errors must fail, and a corrupt winner must remain untouched.

## Fastlane Boundary

The bridge returns `screenshots_path` and `overwrite_screenshots: true` only after local validation.
Preparation runs before external account lookup or upload.
Explicit metadata-only upload bypasses screenshot preparation.
The existing review guard in Mirae and Ttush remains active.
Fastlane replaces all sets in the supplied locales; a partial local locale is not a merge operation.
The later remote adapter must compare complete intended placement groups and read back processing and order.

## Sources

- [Apple screenshot specifications](https://developer.apple.com/help/app-store-connect/reference/app-information/screenshot-specifications/), checked 2026-10-07.
- [Apple asset best practices](https://developer.apple.com/app-store/asset-best-practices/), checked 2026-10-07.
- [Fastlane `2.240.1` screenshot loader](https://github.com/fastlane/fastlane/blob/2.240.1/deliver/lib/deliver/loader.rb), [display-class reader](https://github.com/fastlane/fastlane/blob/2.240.1/deliver/lib/deliver/app_screenshot.rb), and [localized replacement behavior](https://github.com/fastlane/fastlane/blob/2.240.1/deliver/lib/deliver/upload_screenshots.rb), checked 2026-10-07.
- [Fastlane `2.240.1` format and extension validator](https://github.com/fastlane/fastlane/blob/2.240.1/deliver/lib/deliver/app_screenshot_validator.rb), verified against the unpacked source on 2026-10-07.
- [ImageMagick PNG chunk controls](https://imagemagick.org/defines/), checked 2026-10-07.
- QuestKeeper store-asset precedent: `/Users/dongminyu/Development/01_personal/llm-wiki-dongminyu/wiki/sources/claude--projects---users-dongminyu-development-01-personal-quest-keeper--memory--store-assets-pipeline.md`.
  Its stale append/duplicate findings support explicit replacement and later remote readback; its historical device-size advice is superseded by current Apple specifications.
- Mirae `RunnerUITests` precedent: `/Users/dongminyu/Development/01_personal/llm-wiki-dongminyu/wiki/concepts/runner-uitests-load-bearing-name.md`.
  Capture targets and native build pre-actions remain outside this change.
- No relevant project-specific pipeline precedent was returned for Ttush, Kkomkkomi, or Chef al Mando: `[no precedent found]`.
