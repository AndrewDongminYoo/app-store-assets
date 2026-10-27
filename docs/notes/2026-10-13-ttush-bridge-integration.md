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

## Consumer inputs of both runs

The suite copies these files and nothing else from the consumers; `git status --porcelain` showed no change to any of them, and the mirae and kkomkkomi revisions were the same for the before and after runs.

| Consumer           | Revision                                   | File                               | SHA-256                                                            |
| ------------------ | ------------------------------------------ | ---------------------------------- | ------------------------------------------------------------------ |
| mirae              | `9f77e204444cb43e4362dab2bc5a1be0e0de56e8` | `ios/fastlane/Fastfile`            | `e4da2a3ded2d0482015a5d44f13b8588802692f2bfaf818c03cf310a082422b2` |
| mirae              | `9f77e204444cb43e4362dab2bc5a1be0e0de56e8` | `scripts/store_assets/fastlane.rb` | `ce700b76205648cce9b38ff8d3403c85ae1d33423d8f5f60f40c33405ae3431e` |
| kkomkkomi          | `630f26df8c9b91a1476b480d92170a6b6049a8ff` | `fastlane/Fastfile`                | `4622d2f25f6992cdcf0d073b772e242f9f14da33474f9d8070c0c2e093d986b4` |
| ttush_push (after) | `8b6d15da77bca2f3eed87335c818c1a60b81f7a9` | `ios/fastlane/Fastfile`            | `818653cd86c453510a9548a4ceba05cf812e942bf0a9391f59c137ea5dd95919` |

## Reconciliation

The dated unit specifications that require the six Ttush failures to stay explicit (`docs/specs/2026-10-09-legacy-bridge-boundary.md`, `2026-10-09-image-byte-binding.md`, `2026-10-09-public-input-boundaries.md`, `2026-10-10-supplied-byte-reservation.md`, `2026-10-11-review-input-preservation.md`) record what those units had to preserve at the time and are left as written.
For the current integration status, this note supersedes them.
`docs/notes/2026-10-07-stage-1.md` states that the Ttush metadata lane passed the prepared path; ttush_push's history did not contain that change until #177.
