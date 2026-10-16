# Android local bundle verification

## Delivered behavior

The standalone screenshot CLI accepts `--platform android` for Google phone screenshot rules while retaining iOS as the default.
Android bundles have schema version 2, explicit Android platform, and `phoneScreenshots` profiles.
Existing iOS schema version 1 and bundle identities are unchanged.
The extension reuses the frozen catalog and adds no dependency, native toolchain or remote Google operation.
The bundle specification and README document dimensions, encoding, count, partial-bundle limits and platform selection.

Prism Defense adds `merry screenshots prepare-android` using its existing composed phone images, Android package identity and a separate bundle output directory.
Its existing iOS command remains compatible with the installed v1.0.0 runtime.
Android requires the candidate shared checkout selected through `APP_STORE_ASSETS_ROOT`; v1.0.0 was neither modified nor represented as Android-capable.
Local verification completed before committing either repository; the Android-capable runtime remains unpublished.

## Real consumer evidence

The actual consumer commands ran from `/Users/dongminyu/Development/01_personal/prism_defense` with `APP_STORE_ASSETS_ROOT=/Users/dongminyu/Development/01_personal/app-store-assets`:

```sh
merry screenshots prepare-android
merry screenshots prepare
```

The Android command prepared and validated 12 existing 1080×1920 phone screenshots, six each from `en-US` and `ko-KR`.
The bundle identifier is `kr.donminzzi.prism_defense` and its manifest records `unverified-import`.
The bundle is `build/store-assets/android-bundles/2d72bb434445aefb20520133f9b3c5941ecd9abd323a39a085842fc30a304a19` in Prism Defense.
It contains exactly the manifest and the 12 final phone images in copy-manifest order; feature graphics and other source assets are excluded.

The iOS command returned the existing `build/store-assets/bundles/a6f5b52477b8a6180e8977bb67e192f08caf8b2077dcafeda16a32c7e0d78952` unchanged.
The unchanged installed v1.0.0 validator rejected the actual Android bundle at the schema check, confirming that older runtimes do not interpret it as an iOS bundle.
Both bundle manifests hash to their directory names, and every final image hash matches its source hash and actual source bytes.
Repeating both adapters returned the same paths without changing bundle bytes.
All 109 tracked Prism Defense Fastlane files match the baseline from before integration.
The integrity checker rejected an intentionally wrong source hash before accepting the real baseline.
The checker and result are retained under Prism Defense's ignored `build/store-assets/verify-android-integration.py` and `android-integration-verification.json`.

## Tests and review

The new shared CLI test failed before implementation because `--platform android` was unsupported.
All 29 focused bundle tests subsequently passed, covering actual image decoding, Android boundaries, excess images, nested inputs, encoding, alpha normalization, schema/platform mismatches, source preservation, repeated bundles, and legacy iOS identity.
The new consumer test failed before implementation because an Android request still called the iOS source, package and output paths.
All 10 consumer process tests passed after the adapter change.
The consumer fixture checks the real process arguments and selected phone-image inventory while replacing only the external runtime.

Full Prism Defense `flutter analyze` passed with no issues, and all 994 Flutter tests passed.
The final scoped Dart format check reported zero changes.
The repository-wide spelling check inspected 452 files, skipped 15 according to its existing configuration, and reported zero issues.
Two independent reviews covered the shared contract and consumer adapter separately; both returned clear with no actionable findings.
The root also checked the combined default-platform behavior, manifest dispatch, runtime selection, unchanged installed release and actual bundle contents.

### Shared runtime environment diagnostic

The default Python 3.15 full-suite run was not a pass: it completed 428 tests with 56 errors and nine opt-in skips.
One error was the existing derived-bytecode comparison failure, reproduced independently from a pristine archive of starting revision `7ca26d2` with the same Python version.
The other 55 errors rejected unsupported cache tags after overlapping Python 3.14 and 3.15 verification populated the same source tree with both cache formats.
That overlap was a verification error, not evidence of 55 independent product regressions.
The overlapping Python 3.14 run was interrupted and is not counted as verification.

The final shared verification uses a clean temporary snapshot of the candidate, Python 3.14.8, disabled automatic bytecode writes, and the actual personal consumer integration fixtures.
Every overlaid candidate file is hashed against the working source before execution.
The environment selects the same Python version for child commands.
The snapshot is removed by its owning temporary-directory context after the run.
The 22 Python 3.14 caches created during the interrupted run were moved with verified byte preservation to `build/android-local-verification/interrupted-run-python314-caches/`, leaving pre-existing source caches untouched.
The primary checkout's Python 3.15 runtime inventory then passed, confirming that the mixed-cache interference was removed.
The final clean run completed 428 tests in 417.393 seconds with exit code zero: 425 passed and three skipped.
The three skips require the optional real Fastlane 2.240.1 source reader through `APP_STORE_ASSETS_FASTLANE_SOURCE`; the personal consumer integration fixtures were enabled and passed.
After completion, all five candidate file hashes still matched the working checkout, and the comparison rejected an intentionally wrong hash before accepting the real record.
The final log is `build/android-local-verification/clean-python314-integration.log`, and `clean-candidate.json` records the tested hashes, Python version, command and exit code.

Diagnostic and verification logs are retained under this repository's ignored `build/android-local-verification/` directory.
The known Python 3.15 cache compatibility issue was not changed as part of Android screenshot support.

## Precedent and limits

Oracle returned no verified project-specific Android bundle precedent: `[no precedent found]`.
The global precedent `wiki/concepts/ecosystem-agnostic-skill-design.md` supports explicit platform selection by analogy, confirming the choice of a declared CLI option rather than image-size inference.
`wiki/sources/claude--skills--using-android-skills--skill.md` supports keeping image packaging outside native Android tooling.
Retrieval was partial and current wiki freshness was unverified.
Source preservation follows this repository's current `AGENTS.md` and existing bundle contract, rather than an inferred Oracle rule.

The checked [Google Play preview asset requirements](https://support.google.com/googleplay/android-developer/answer/9866151?hl=en) support the phone image rules; this is not complete listing or store acceptance validation.
No new capture, native build, Google Play state read, upload, review submission or release publication was performed.
Existing screenshots were not promoted to verified native-capture provenance.

## Reproduction

Use an Android-capable reviewed checkout with the consumer command:

```sh
APP_STORE_ASSETS_ROOT=/absolute/path/to/app-store-assets merry screenshots prepare-android
```

For shared tests, use one Python version in a clean source snapshot and disable automatic bytecode writes:

```sh
PATH="/opt/homebrew/opt/python@3.14/libexec/bin:$PATH" PYTHONDONTWRITEBYTECODE=1 APP_STORE_ASSETS_PERSONAL_ROOT=/absolute/personal/root python3 -B -m unittest discover -s tests -v
```

The tests evaluate copied Fastfiles and substitute external actions; they do not execute live release lanes.
