# Screenshot Bundles, Protocols 1 and 2

## Scope

Prepare existing personal iOS screenshots and Android phone screenshots for local validation and downstream tools.
Preserve native project capture, native composition, source bytes, previous bundles, and unrelated changes.
No store login, upload, publishing, review submission, device install, or simulator build is part of preparation.

## Input and Output

The source has locale folders containing PNG or JPEG images.
Mirae supplies `images/iphone65` as the subdirectory within each locale.
Reject an empty source, unsupported resolution, alpha channel or malformed pixel stream.
The default platform is iOS; reject more than ten images per locale and legacy display class.
Reject hidden screenshot filenames because Fastlane skips them.
Allow only `.png`, `.PNG`, `.jpg`, `.JPG`, `.jpeg`, and `.JPEG`, and require the decoded image format to match the extension.
PNG alpha normalization is opt-in and requires every pixel to be opaque.
Do not invent a background for transparent artwork.
Exclude generated PNG date and time chunks; retain color metadata.
Reproducibility applies within the same ImageMagick runtime, not across encoder versions.

Create a separate content-addressed bundle with `manifest.json` and `screenshots/<locale>/<filename>`.
The iOS manifest contains `schema_version: 1`, personal account scope, project, bundle identifier, replacement policy, and assets with original and final SHA-256, final dimensions, locale, kind, and display profile.
Explicit `--platform ios` produces the same manifest bytes and content-addressed identity as omitting the option.
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

## Android Phone Bundles

`--platform android` selects the frozen catalog's Google `phoneScreenshots` rule.
Require dimensions from 320 to 3840 pixels inclusive, longest edge at most twice the shortest, and no more than eight images per locale.
Accept JPEG and 24-bit RGB PNG without an alpha channel.
Reject indexed, grayscale and 16-bit PNG rather than silently converting them.
The existing optional normalization only removes an unused alpha channel from an opaque PNG and produces 24-bit RGB output.
The iOS-specific mixed `_framed` filename filter does not apply to Android.

Android manifests use `schema_version: 2`, explicitly require `platform: android`, and record profile `phoneScreenshots`.
The existing `bundle_id` field carries the Android package name.
Version 1 stays iOS-only; unknown schema/platform combinations fail.
An older validator rejects schema 2 before using Apple dimensions.
The bundle keeps the same locale/file layout, final/source hashes, atomic publication, byte-preserving reuse and `unverified-import` provenance.

The source subdirectory may be `images/phoneScreenshots`, which excludes sibling icon and feature-graphic files.
A nonempty local bundle may have only one image; the store's minimum of two screenshots across device types belongs to publication completeness, not this local preparation contract.
Tablet, TV, watch, XR, icon and feature-graphic bundles are not introduced.
No remote Google Play adapter, store discovery, upload plan or publication guarantee is added.

## Fastlane Boundary

The legacy `AppStoreAssets.prepare` entrypoint fails before local process launch and cannot return screenshot transfer options.
The Ruby local preparation helper and guarded remote bridge remain iOS-only.
`AppStoreAssets.prepare_local` explicitly performs local validation/preparation and returns a prepared path without an overwrite flag.
A locally prepared path does not authorize remote replacement.
No authenticated transfer, planner or runtime launcher is introduced by this boundary.
Actual consumers that directly call Fastlane remain separate consumer work; all three personal consumers passed the opt-in integration checks at the revisions recorded in [the 2026-10-14 integration evidence](../notes/2026-10-14-mirae-direct-lanes-integration.md).
The Mirae fixture copies its required local helper and checks its plan/digest requirement, including metadata-only calls, as defined by the [fixture contract](2026-10-16-fastlane-integration-fixture.md).
The separate guarded transfer adapter binds a reviewed plan/digest to the exact target, compares declared placement groups and reads back processing and order; [the guarded screenshot transfer specification](2026-10-14-guarded-screenshot-transfer.md) defines that contract.

## Sources

- [Google Play preview asset requirements](https://support.google.com/googleplay/android-developer/answer/9866151?hl=en), checked 2026-10-16; the phone screenshot rules agree with the existing frozen catalog.
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
