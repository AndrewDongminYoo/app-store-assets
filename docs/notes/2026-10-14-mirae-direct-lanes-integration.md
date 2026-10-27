# Mirae direct-lane integration evidence (2026-10-14)

The opt-in Fastlane integration suite (`tests/test_fastlane.py`) passes for all three personal consumers after Mirae dropped its pinned store runtime pilot.
Mirae's iOS `metadata` lane now loads this repository's bridge the way the Ttush and Kkom lanes do, so its metadata-only run succeeds instead of stopping.

## Before

- app-store-assets `e822b8b`, mirae `ios/fastlane/Fastfile` at `620befe4`, ttush_push and kkomkkomi as in the table below.
- Command: `APP_STORE_ASSETS_PERSONAL_ROOT=<temporary personal root> python3 -m unittest discover -s tests -p 'test_fastlane.py'`.
- Result: `Ran 5 tests`, `FAILED (errors=6)`, every error a mirae subtest of `test_legacy_metadata_lanes_are_blocked_before_replacement`, `test_invalid_images_stop_before_upload_or_account_lookup`, `test_metadata_only_option_does_not_require_a_screenshot_tool`, and `test_reader_incompatible_inputs_stop_before_external_calls` for `hidden screenshot`, `format` and `extension`.
- Cause: the test still copied mirae's `scripts/store_assets/fastlane.rb`, which AndrewDongminYoo/mirae#204 removed, and still expected Mirae's metadata-only run to stop.

## Change

AndrewDongminYoo/mirae#204 (merge commit `620befe4`, merged 2026-10-14) restores Mirae's direct Fastlane lanes, makes the iOS `metadata` lane call `AppStoreAssets.prepare` on `fastlane/metadata/ios/<locale>/images/iphone65` before the review lookup and before `deliver`, keeps `skip_screenshots: true` as the metadata-only path, and passes `skip_screenshots: true` in the `release` lane.
The test now copies only Mirae's `ios/fastlane/Fastfile` and expects its metadata-only run to succeed with `skip_screenshots` set, like the other two consumers.

## After

- Same command and inputs with the updated test: `Ran 5 tests`, `OK`.

## Consumer inputs of both runs

The suite copies these files and nothing else from the consumers.
The temporary personal root held the mirae file written from `git show 620befe4:ios/fastlane/Fastfile` and the ttush_push file fetched for the 2026-10-13 run, and linked kkomkkomi's existing checkout, whose `fastlane/Fastfile` had no local change.
mirae `main` at `85da2688` has the same `ios/fastlane/Fastfile` as `620befe4`.

| Consumer   | Revision                                   | File                    | SHA-256                                                            |
| ---------- | ------------------------------------------ | ----------------------- | ------------------------------------------------------------------ |
| mirae      | `620befe4a1aa433f2c323011b76bcb40d5689ebb` | `ios/fastlane/Fastfile` | `c1c7ba02333f6c1b2dfbdb81394abfe4316cfc785d43e4cbd14bc0910cbc9cde` |
| ttush_push | `8b6d15da77bca2f3eed87335c818c1a60b81f7a9` | `ios/fastlane/Fastfile` | `818653cd86c453510a9548a4ceba05cf812e942bf0a9391f59c137ea5dd95919` |
| kkomkkomi  | `630f26df8c9b91a1476b480d92170a6b6049a8ff` | `fastlane/Fastfile`     | `4622d2f25f6992cdcf0d073b772e242f9f14da33474f9d8070c0c2e093d986b4` |

## Reconciliation

`docs/notes/2026-10-13-ttush-bridge-integration.md` records the Mirae inputs of that day, when the pilot helper `scripts/store_assets/fastlane.rb` made Mirae's lanes stop with the "reviewed plan" error; it is left as written, and this note supersedes it for the current Mirae status.
Mirae's Android lanes do not load this repository and are outside the suite.
