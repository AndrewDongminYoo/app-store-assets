# Android local screenshot bundles

## Scope and approval

The operator requested Android local bundle preparation and validation after the Prism Defense iOS integration.
Extend the shared standalone CLI and the existing Prism Defense adapter in their current primary checkouts.
Preserve source images, previous bundles, existing iOS behavior, and app-owned capture and composition.
Google Play reads, uploads, release operations, native builds, tablet assets, icons and feature graphics are outside this change.
Publication of this new shared-runtime change is not part of local verification.

## Contract

Add `--platform android` to `assets.py prepare-screenshots`; omission and `--platform ios` preserve the existing iOS manifest bytes and paths.
Android uses the existing frozen Google `phoneScreenshots` catalog rule: 320–3840 pixels per dimension, longest edge at most twice the shortest, and at most eight images per locale.
Android PNG input must be 24-bit RGB without alpha; JPEG is also supported.
Existing explicit normalization may remove an unused alpha channel but must not create a background for transparent pixels.
Local bundles may contain one image; the store's publication minimum across device types is not a local file-validation claim.

Android bundles use schema version 2 with an explicit `platform: android` and `phoneScreenshots` profile.
This makes older validators reject them instead of treating them as Apple bundles.
Version 1 remains the unchanged iOS format.
Validation selects rules from the manifest and rejects unknown schema/platform combinations.
Both platforms retain final/source hashes, original paths, immutable publication and `unverified-import` provenance.

Prism Defense retains `merry screenshots prepare` for iOS and adds `merry screenshots prepare-android`.
The Android adapter reads only `fastlane/metadata/android/{en-US,ko-KR}/images/phoneScreenshots`, requires the filenames from `copy.tsv`, uses Android package identity `kr.donminzzi.prism_defense`, and writes to `build/store-assets/android-bundles`.
The adapter validates the returned bundle and propagates failures.
Until an Android-capable runtime is published, use `APP_STORE_ASSETS_ROOT` to select this reviewed local checkout; do not claim v1.0.0 contains this feature or modify its installed checkout.

## Work and verification

1. Add shared CLI regression tests and observe Android preparation fail before implementation.
   Cover actual decoded dimensions, aspect ratio, count, alpha/encoding, manifest platform, nested source selection, byte preservation, repeated bundles and legacy iOS equivalence.
2. Implement the platform branch using the existing Google slot catalog, and update README and the bundle specification.
   Run `python3 -m unittest discover -s tests -v` and the declared opt-in consumer integration suite.
3. Extend the Prism Defense process tests before its adapter and command wiring.
   Check actual platform-specific source, locale, output, package arguments, incomplete Korean Android inventory and runtime failures.
4. Exercise both real adapters with the candidate shared runtime.
   Compare all original tracked Fastlane file hashes, previous iOS bundle bytes and the new 12-image Android bundle.
5. Run scoped Dart formatting, full `flutter analyze`, full Flutter tests, spelling checks and one structured final diff review.
   Record results and remaining publication limitations in `docs/notes/`.

## Completion

The shared CLI and Prism Defense adapter are implemented and verified locally.
Both real adapters produced valid immutable bundles, preserving the previous iOS bundle and all 109 tracked Fastlane source files.
The clean Python 3.14 integration run passed 425 tests with three optional real-reader skips; all 994 Prism Defense Flutter tests and static analysis passed.
The Python 3.15 baseline cache issue, interrupted verification run, source integrity evidence and review outcomes are recorded in [the verification note](../notes/2026-10-16-android-local-bundles.md).
The Android-capable runtime remains unpublished; PR publication does not make it part of the installed v1.0.0 release.

## Sources

- Existing `assets.py`, `tests/test_assets.py` and `docs/specs/screenshot-bundles.md` establish iOS compatibility and immutable publication.
- Existing `catalog/store-rules-v1.json` defines the supported Google phone slot; its frozen identity remains unchanged.
- [Google Play preview asset requirements](https://support.google.com/googleplay/android-developer/answer/9866151?hl=en), checked 2026-10-16, confirm phone screenshot dimensions, aspect ratio, encoding and maximum count.
- Prism Defense's `README.md`, `copy.tsv` and Android output directories establish the app-owned source layout.
- Oracle found no verified project-specific precedent for Android bundles: `[no precedent found]`.
  Its global `wiki/concepts/ecosystem-agnostic-skill-design.md` supports explicit platform selection by analogy, and `wiki/sources/claude--skills--using-android-skills--skill.md` confirms that image packaging does not require native Android tooling.
  Retrieval was partial and current wiki freshness was unverified; repository contracts and the checked official rules govern the actual validation requirements.
