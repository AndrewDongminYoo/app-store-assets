# Fastlane Integration Fixture Plan

The [specification](../specs/2026-10-16-fastlane-integration-fixture.md) defines the correction for [issue #41](https://github.com/AndrewDongminYoo/app-store-assets/issues/41).
The operator requested this PR loop after the current Mirae contract conflict was reported.

## Owned Paths

- `tests/test_fastlane.py`
- `tests/test_fastlane_fixture.py`
- This plan and its specification

## Steps

1. Reproduce the current opt-in Mirae loading failures.
   Add default-suite regressions for local-helper loading and invalid JSON diagnostics before changing the fixture.
2. Copy the required actual Mirae helper into the temporary checkout.
   Report JSON decoding failures with subprocess evidence.
   Separate Mirae's metadata-only rejection from the other consumers' metadata-only success cases.
3. Run the focused default and opt-in tests, then both full suites with Python 3.12 as used by CI.
   Use a fresh temporary source copy if local interpreter caches conflict with runtime-integrity tests.
   Compare the tested files with the candidate before committing.
4. Perform one structured local review of the complete diff and the unchanged Ruby harness boundaries.
   Commit the fixture correction as one concern, publish the PR, and observe current-head CI and hosted reviews until the operator merge boundary.

## Verification

```bash
python3 -m unittest discover -s tests -p 'test_fastlane*.py' -v
APP_STORE_ASSETS_PERSONAL_ROOT=/Users/dongminyu/Development/01_personal python3 -m unittest discover -s tests -p 'test_fastlane*.py' -v
python3 -m unittest discover -s tests -v
APP_STORE_ASSETS_PERSONAL_ROOT=/Users/dongminyu/Development/01_personal python3 -m unittest discover -s tests -v
git diff --check
```

Synthetic fixtures test the copy and diagnostics mechanisms without personal checkouts.
The opt-in suite checks the current consumer Fastfiles and helper code with external actions stubbed.
Neither suite establishes a successful live upload.
