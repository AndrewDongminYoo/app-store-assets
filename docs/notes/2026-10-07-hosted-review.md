# Hosted review verification

Review of `c326d638026ff95a8e3949e1f3a07630c5705db1` reported six findings.
Five were reproduced with synthetic inputs before repair:

- Ruby 4.0 JSON parsing failed on Korean text under the sanitized C locale.
- Download staging omitted an explicitly declared Gemfile and Gemfile.lock.
- Listing plans accepted a different account identity or Google track.
- Metadata and image plans could omit a listing entirely.
- A killed executor left a permanent file lock, preventing receipt inspection.

Adapters now use UTF-8; the native Ruby entrypoint also sets stdin to UTF-8.
Planning and download share the declared provider input inventory, including the frozen Ruby dependency files.
Listing operations require a listing with the complete selected target identity.
Execution uses a nonblocking OS advisory lock on a persistent inode on macOS/Linux.
Process exit releases ownership; a pending or partial durable receipt still blocks blind retries.
The lock inode is never unlinked, avoiding two owners locking different inodes at the same path.

The sixth claim, that pinned Fastlane AppInfo has `app_info_state` instead of `state`, does not match the installed 2.240.1 source.
Its `AppInfo` model exposes `state`, and `App#fetch_edit_app_info` uses that accessor.
A regression loads the actual model and Fastlane version file, replaces transport/token construction with offline stubs, and verifies editable AppInfo selection and Korean name retrieval.
No SDK authentication or store request runs in this test.

Verification: 134 tests passed with all optional personal Fastfile and installed SDK checks enabled; zero skipped.
The original C-locale, staging, target, missing-listing and killed-process regressions failed before their corresponding repairs.
Actual native builds, signing and live store behavior remain unverified.

## Reviewed provider binding and download completeness

The next bounded repair covers four reproduced findings on `6cf010f09d1a073c61fea921f42d8c89bf933d22`:

- Ruby bare and nested relative `load` calls could resolve replaced working-directory files. The resolver now selects captured bytes for working-directory and load-path names and rejects an added staged helper.
- Execution constructed a provider from an earlier profile read even when plan verification later observed the reviewed profile. Execution and readback now construct from the reviewed target, mode, complete adapter descriptor and executable identity. Execution rejects mismatched command-provider objects before creating an attempt; stage binding freezes the reviewed configuration.
- Google binary changelog locale keys were not validated offline. They now use the existing listing locale contract before reading notes or invoking a provider.
- Google download compared only images still present in its second read. It now compares both complete ordered inventories before the first image download, then consumes the frozen second read without a third lookup.

Regression tests first demonstrated all four failures, using temporary public inputs and stubbed external boundaries. The profile race test executes real temporary approved/unreviewed adapters; the download test covers removed locales, empty groups, removed/reordered/added images and an unchanged inventory. No credential read, live authentication, store call, signing or native build is part of this evidence.

Current validation: 173 tests discovered; the default suite passes 162 with 11 optional skips, and the installed Fastlane 2.240.1 source suite passes 168 with five personal-Fastfile integration skips. Ruby syntax, scoped Ruff and whitespace checks pass. Personal Fastfile integrations are not rerun in this repair: the preceding run had six Mirae missing-helper subcase errors because the temporary fixture copied its Fastfile without the newly required app-owned helper. Those errors remain a reported fixture limitation, not a passing integration result.
