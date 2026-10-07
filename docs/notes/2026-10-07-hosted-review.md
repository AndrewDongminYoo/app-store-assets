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
