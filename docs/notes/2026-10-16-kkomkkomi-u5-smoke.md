# Kkomkkomi U5 screenshot transfer evidence

The authorized U5 smoke run completed on 2026-10-16 for `kr.donminzzi.kkomkkomi`, Apple iOS production `1.1.1 (5)`.
Both declared groups, `en-US/APP_IPHONE_67` and `ko/APP_IPHONE_67`, were replaced once with four images each.
The adapter's final read and a separate live read confirmed the expected count, ordered provider checksums, completed image processing, and unchanged version/build state.
The machine-readable [execution and final-read evidence](2026-10-16-kkomkkomi-u5-smoke.json) records the result and new screenshot IDs.

## Scope and identity

- Account: personal.
- App Store app ID: `6818927076`.
- App Store version ID: `e427f7af-3793-4505-b96d-a16ae527070d`.
- Attached build ID: `5f0f7a3e-879e-400c-849f-81fdf9b4a570`, `1.1.1 (5)`, processing state `VALID`.
- Consumer source: `269332d5c9f9c9941f4a9265f96a5ff9ef34f9fc`, merged in [kkomkkomi PR #109](https://github.com/AndrewDongminYoo/kkomkkomi/pull/109).
- Adapter runtime: `bfae59e569434de5c3ca20b03b95f7fa66b73e38`.
- Installed transport for this live run: fastlane `2.241.0`.
- Executed plan digest: `1b8729c7a297963baf757edd2c13fa5717ed772cb67eaeca61135aab3c841256`.
- Asset snapshot ID: `8238321d2e504886df09520f4ccadfcc0e40464e83758b4e63e6eae25edb3091`.
- Asset provenance: `unverified-import`, unchanged after transfer.

The binary prerequisite was completed under separate operator authorization: build 5 was uploaded, processed, and attached before screenshot execution.
The screenshot run did not upload a binary, change metadata text, submit review, or publish a release.
The target remained editable with no active review in the final live read.

## Approval and observed refusal

The operator first approved a read-only-verified, upload-only run with `allow_delete: false` and an exclusive writer window.
That run refused before any remote write because the populated English group differed from the planned checksums.
A separate read confirmed the full supplied snapshot was unchanged.
In both locales the first two image checksums differed, while the last two matched.

The existing adapter replaces an entire declared group, so four differing positions required replacement of eight placements.
The operator reviewed the proposed images and new plan, then explicitly authorized one replacement and the exclusive writer window.
The new plan set `allow_delete: true` for the two declared groups only.
Its read-only check passed before execution; the old approval was not reused.
Each approved plan was executed once, and the replacement succeeded on its only attempt.

The eight prepared image bytes, dimensions, and order matched the earlier intended asset manifest.
No native-capture claim was added.
The operator's local review package preserves the original images, contact sheet, both plans, approval records, and full live observations; the committed JSON contains the public result without credentials or local credential paths.

## Final provider readback

The following ordered MD5 values were read from App Store Connect after execution and matched the prepared image bytes.
All screenshot IDs also matched the adapter's successful result.

| Locale | Position | Screenshot ID | Provider MD5 | State |
| --- | --- | --- | --- | --- |
| en-US | 1 | `39400019-6709-81e4-8005-b5a992fa8414` | `1ecb1cdf476ae6158579e3e79428345f` | COMPLETE |
| en-US | 2 | `87000019-6709-81e4-8022-d0c0da21550a` | `dc0f942aa4991b2afe4eb3e8f74863a4` | COMPLETE |
| en-US | 3 | `c8000019-6709-81e4-8018-b2321bbe9eff` | `c8d00bcede8ab0f49562e96ff0507c18` | COMPLETE |
| en-US | 4 | `25800019-6709-81e4-803d-7bbfcfdb18ef` | `938e5ae2cd59341a759b206dcd3d9058` | COMPLETE |
| ko | 1 | `4f800019-6709-81e4-8000-deda8b653bfb` | `96d5f862ebd6c4dad1f71a5edf1596ef` | COMPLETE |
| ko | 2 | `3b400019-6709-81e4-8037-59a94a549e18` | `95f108b049028de4fcc70ffe5f97eb06` | COMPLETE |
| ko | 3 | `31800019-6709-81e4-802c-02cb6b35efee` | `d8f79810ace4ddf3e4af967a33d7dc8f` | COMPLETE |
| ko | 4 | `73400019-6709-81e4-8034-88f2bf4ef15e` | `7f0916f743925deed4179f92a001aaeb` | COMPLETE |

The two declared locales had no additional screenshot sets before or after the run: the preserved sets were `{"en-US": {}, "ko": {}}`.
This smoke run verifies that empty preserved-set case; it does not demonstrate preservation of a non-empty additional set on the live service.
The complete non-image snapshot matched before and after, including the approved build and inactive review state.

## Verification

The live acceptance checks were the adapter's guarded transfer result and a separate snapshot/checksum read, not the upload helper's success message.
A local check of the final provider data first rejected an intentionally wrong checksum, then passed for the actual observed checksums and processing states.
The screenshot replacement was the separately authorized smoke operation, not a real release lane used as a regression test.

Using Python 3.12 in copies of the candidate without bytecode caches, `python3 -B -m unittest discover -s tests -v` passed 417 tests with 9 skips.
The same command with `APP_STORE_ASSETS_PERSONAL_ROOT=/Users/dongminyu/Development/01_personal` passed 417 tests with 3 skips.
Both Ruby bridge files passed `ruby -c`.
The candidate source and the four actual consumer input files had identical hashes before and after those runs.
The default suite uses fake provider actions; opt-in integration evaluates the personal consumers' actual Fastfiles while replacing external actions.
Those suites do not establish the live App Store result above.

## Contract and limits

This completes [U5 of the approved plan](../plans/2026-10-14-guarded-screenshot-transfer.md#u5-authorized-smoke-upload-for-kkomkkomi) under the [transfer specification](../specs/2026-10-14-guarded-screenshot-transfer.md).
It is evidence for this target, plan, provider version, and observation time, not permission to repeat the run or transfer another app's assets.
Any future operation needs its own current snapshot, matching plan/approval, and operator-authorized scope.
