# Ttush bridge integration evidence (2026-10-13)

The opt-in Fastlane integration suite (`tests/test_fastlane.py`) now passes for all three personal consumers.
The six Ttush safety subcases that the 2026-10-09 to 2026-10-11 unit specifications kept visible no longer fail.

## Before

- app-store-assets `5e3548a`, ttush_push `d91dc12`, existing mirae and kkomkkomi checkouts.
- Command: `APP_STORE_ASSETS_PERSONAL_ROOT=/Users/dongminyu/Development/01_personal python3 -m unittest discover -s tests -p 'test_fastlane.py' -v`.
- Result: `Ran 5 tests`, `FAILED (failures=6)`, every failure a ttush_push subtest with `AssertionError: 0 == 0` (the lane succeeded where it must stop).
- The failing cases were `test_legacy_metadata_lanes_are_blocked_before_replacement`, `test_invalid_images_stop_before_upload_or_account_lookup`, `test_legacy_alpha_inputs_do_not_authorize_replacement`, and `test_reader_incompatible_inputs_stop_before_external_calls` for `hidden screenshot`, `format` and `extension`.
- Cause: ttush_push's `ios/fastlane/Fastfile` called `deliver` directly and never loaded the bridge; no ttush_push ref or stash had ever contained it (`git log --all -S AppStoreAssets` and `-S app-store-assets` were empty).

## Change

AndrewDongminYoo/ttush_push#177 (merge commit `8b6d15d`, merged 2026-10-13) makes the iOS `metadata` lane call `AppStoreAssets.prepare` before the review lookup and before `deliver`, keeps `skip_screenshots: true` as the metadata-only path, and passes `skip_screenshots: true` in the `release` lane.
No app-store-assets file changed for it.

## After

- app-store-assets `e1e27e2`, ttush_push `ios/fastlane/Fastfile` at `8b6d15d` fetched through the GitHub API into a temporary personal root, mirae and kkomkkomi linked from their existing checkouts.
- Same command with `APP_STORE_ASSETS_PERSONAL_ROOT` pointing at that root: `Ran 5 tests`, `OK`.
- The suite copies only `ios/fastlane/Fastfile` from ttush_push, so the fetched file is the whole Ttush input it reads.

## Reconciliation

The dated unit specifications that require the six Ttush failures to stay explicit (`docs/specs/2026-10-09-legacy-bridge-boundary.md`, `2026-10-09-image-byte-binding.md`, `2026-10-09-public-input-boundaries.md`, `2026-10-10-supplied-byte-reservation.md`, `2026-10-11-review-input-preservation.md`) record what those units had to preserve at the time and are left as written.
For the current integration status, this note supersedes them.
`docs/notes/2026-10-07-stage-1.md` states that the Ttush metadata lane passed the prepared path; ttush_push's history did not contain that change until #177.
