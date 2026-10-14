# Guarded Screenshot Transfer Plan

Operator-approved plan, 2026-10-14, for [issue #28](https://github.com/AndrewDongminYoo/app-store-assets/issues/28).
[The specification](../specs/2026-10-14-guarded-screenshot-transfer.md) owns the contract as numbered invariants; this plan owns the order of work, the provider details, and the acceptance tests that hold each unit to those invariants.

## Decisions

- Scope of the first pull request: the specification and this plan only, with no code.
- Transport: Ruby Spaceship from fastlane 2.240.1, inside `lib/fastlane_assets.rb`.
- First target app for offline-profile v1: kkomkkomi.
- After the first draft (pull request #30) reached the review-loop round limit, the specification keeps only invariants, and step order and provider behavior live here as tests (operator decision, 2026-10-14).

## Rules for every unit

- Each unit is a separate pull request, in the order below, and starts only after the previous unit has merged.
- `python3 -m unittest discover -s tests -v` and `ruby -c lib/fastlane_assets.rb` pass at every unit; the default suite needs no fastlane gem, no network and no credentials.
- No unit except U5 makes a real App Store Connect call; tests use the fake App Store Connect that [the specification's verification section](../specs/2026-10-14-guarded-screenshot-transfer.md#verification) requires.
- Each new guard has a test that fails when the guard is removed, and each test names the specification invariant it holds.
- No unit adds a service, a database, a capture abstraction or a Python dependency.

## Provider behaviors

These fastlane 2.240.1 behaviors were read from the installed gem source on 2026-10-14.
Each row names the invariant it affects and what U3 or U4 must do about it; the implementation re-checks each against the pinned source before relying on it.

| Behavior in 2.240.1 | Invariant | Required handling |
| --- | --- | --- |
| `AppScreenshot` reports `source_file_checksum` as `Digest::MD5.hexdigest` of the uploaded bytes ([`app_screenshot.rb`](https://github.com/fastlane/fastlane/blob/2.240.1/spaceship/lib/spaceship/connect_api/models/app_screenshot.rb)). | 2, 7 | Compute the planned MD5 from the SHA-256-checked bytes and compare readback against it. |
| `AppScreenshotSet#upload_screenshot(path:, wait_for_processing: true, position: nil)` waits for processing every 2 seconds with no deadline by default, and repositions with an `Array#insert` on the set's current IDs ([`app_screenshot_set.rb`](https://github.com/fastlane/fastlane/blob/2.240.1/spaceship/lib/spaceship/connect_api/models/app_screenshot_set.rb)). | 6, 7 | Pass `wait_for_processing: false`, give each image an explicit position, and let the adapter's own bounded poll (default 5 seconds apart, 600 seconds per group) gate processing. |
| When placeholder creation raises, `AppScreenshot.create` retries every 30 seconds until `SPACESHIP_SCREENSHOT_UPLOAD_TIMEOUT` minutes pass (default 20, uncapped from the environment), printing a line with `puts` on each retry. | 6, 8 | Set that variable to the group limit in whole minutes (at least 1) while provider calls run and restore it afterwards; send provider output to standard error. |
| `FileUploader.upload` sends each upload operation with a `SPACESHIP_TIMEOUT` request timeout (default 300 seconds) and up to 5 tries, 3 seconds apart ([`file_uploader.rb`](https://github.com/fastlane/fastlane/blob/2.240.1/spaceship/lib/spaceship/connect_api/file_uploader.rb)). | 6 | Set `SPACESHIP_TIMEOUT` to a bounded value (default 60 seconds) while provider calls run and restore it afterwards. |
| A screenshot set that does not exist must be created with `AppStoreVersionLocalization#create_app_screenshot_set(client: nil, attributes:)` before `upload_screenshot` can be called, as deliver's [`app_screenshot_iterator.rb`](https://github.com/fastlane/fastlane/blob/2.240.1/deliver/lib/deliver/app_screenshot_iterator.rb) does ([`app_store_version_localization.rb`](https://github.com/fastlane/fastlane/blob/2.240.1/spaceship/lib/spaceship/connect_api/models/app_store_version_localization.rb)). | 4 | Create a set only for a declared group with no remote set, on that locale's live localization, with `screenshotDisplayType` set to the declared slot. |
| Selecting another build for a version keeps the version's ID and name; `AppStoreVersion#get_build` returns the attached build, whose `version` is the build number ([`app_store_version.rb`](https://github.com/fastlane/fastlane/blob/2.240.1/spaceship/lib/spaceship/connect_api/models/app_store_version.rb), [`build.rb`](https://github.com/fastlane/fastlane/blob/2.240.1/spaceship/lib/spaceship/connect_api/models/build.rb)). | 3, 7 | Read the attached build in the live read and in the final read, and compare its number with `target.version.build`. |
| `AppScreenshot` exposes `complete?`, `error?`, `error_messages` and `asset_delivery_state`, and processing state can lag right after an upload. | 3, 5, 7 | Treat a group as unchanged only when every screenshot is complete, polling within the bound first; an errored screenshot refuses the run. |

## U1: kkomkkomi offline-profile v1

Repository: kkomkkomi.

The current `store-upload.json` uses an older schema with the top-level keys `account`, `apple`, `google`, `gemfile` and `remote`, which `load_profile` rejects.
Offline-profile v1 requires exactly `schema_version`, `type`, `project`, `mode`, `runtime` and `targets`.

Work:

1. Add a v1 profile with one Apple iOS images target, including a `replacement` policy, a public listing, a supplied `metadata-snapshot` and an asset snapshot.
2. Put the v1 profile at a new path and pass it with `--profile`.
   The CLI's default `--profile` is `store-upload.json`, and kkomkkomi's `tool/build_record.sh`, `AGENTS.md` and `CLAUDE.md` still reference the existing file.
3. Keep the existing file and lanes unchanged until a later decision retires them.

Acceptance:

- `python3 -B -m app_store_assets plan --root <kkomkkomi> --profile <v1 profile> --target <name> --operation images` returns a plan with `remote_evidence: supplied-snapshot-freshness-unverified`.
- `replacement.locales` and `replacement.slots` equal the listing's locales and slots, so `make_plan` accepts the policy.
- No store call, no credential and no change to the kkomkkomi Fastfile lanes.

## U2: Approval record

Repository: app-store-assets (Python only).

Work:

1. Add the `transfer-approval` record that [the specification](../specs/2026-10-14-guarded-screenshot-transfer.md#approval-record) defines, with exact-key validation.
2. Add a read-only verification command: run `verify_plan`, validate the approval record against the verified plan, check every planned image's SHA-256, and print the verified intent as JSON (invariants 1 and 2).
3. Add the record's structural summary to `schemas/` and keep the Python validator authoritative.

Acceptance:

- A changed plan input, a different `plan_digest`, a different target field, a missing `account_id` when the plan has one, a different operation, an unknown key and a credential-shaped path each fail with a distinct error.
- An image that changed after planning fails, whichever declared group it belongs to.
- The plan payload type, `executable: false` and `effects: []` are unchanged, and the reader package still constructs no provider.

## U3: Read-only live readback

Repository: app-store-assets (Ruby entrypoint, tests driven from Python as `tests/test_bridge.py` does).

Work:

1. Add the new Ruby entrypoint with a read-only mode that loads Spaceship only inside it.
2. Take an exclusive lock file for the target's bundle identifier under the system temporary directory, with create-new semantics, before the U2 command and the live read, and remove it when the run ends; an existing lock refuses the run and is removed only by the operator.
3. Call the U2 command through `Open3`, then read the app, the version, its attached build, the localizations of the declared locales, the declared groups and the preserved sets.
4. Compare with the supplied snapshot (invariant 3), defining and testing the mapping of each snapshot field to a Spaceship value, and print the per-group result as JSON with provider output on standard error (invariant 8).
5. Add the fake App Store Connect to the tests.

Acceptance (fake states):

- A different `version_id`; a version that is not editable or has an active review; an attached build that differs from the approved one or is missing while the version name and ID stay the same; a changed screenshot ID or order; a group present on one side only; a snapshot field with no mapping: each refuses and names the group.
- An existing lock file refuses before any Spaceship call.
- The read-only mode makes no remote write; the test asserts the fake's call log.
- `AppStoreAssets.prepare` stays blocked.

## U4: Transfer mode

Repository: app-store-assets (Ruby entrypoint, fake-tested).

Work:

1. Add a transfer mode to the U3 entrypoint that keeps one lock from the U2 command through the final read.
2. Settle every check, every group's action and the health of every unchanged group before the first remote write (invariant 5).
3. Write only declared groups, following the [provider behaviors](#provider-behaviors): create absent sets, upload the checked bytes from private temporary copies with explicit positions, and replace a group only under `allow_delete`.
4. Poll each group within the bound, read back count, MD5 order and processing, and reorder once when only the order differs.
5. Do the final read of invariant 7.

Acceptance (fake states, each with the outcome the specification's invariants require):

- A non-empty, different group with `allow_delete: false` refuses before the first write, also when an earlier group would only upload.
- A matching group with an errored screenshot refuses before the first write; a matching group that is still processing passes only after its bounded poll, before the first write.
- A declared group with no remote set passes after exactly one `create_app_screenshot_set` call on its localization with its slot, then the upload into the new set.
- A processing state or checksum that is late but correct within the bound passes; one that errors, stays incomplete or stays empty fails at the bound.
- A checksum that differs from the planned MD5 fails; an order that differs only after upload passes after exactly one `reorder_screenshots` call and fails if it still differs.
- A placeholder creation that keeps failing, and a successful creation followed by upload requests that time out, each end within the configured bounds and restore both environment variables.
- A preserved set, a declared group after its own readback, or the attached build or version state that changes during the run fails the final read.
- No create, upload, delete or reorder call reaches a preserved set, an undeclared locale, or a declared slot of a declared locale that the listing does not pair; the test asserts the fake's call log.
- A provider call that prints to standard output leaves exactly one JSON document on standard output.
- Provenance stays `unverified-import`.

## U5: Authorized smoke upload for kkomkkomi

Repository: app-store-assets, run against the U1 kkomkkomi profile.

Preconditions:

- U1 to U4 have merged.
- The operator meets the [specification's operator preconditions](../specs/2026-10-14-guarded-screenshot-transfer.md#operator-preconditions) for kkomkkomi: authorization for each operation of this run, and the writer window for the whole run.
- A fresh supplied snapshot, a fresh plan and a new approval record exist for this run.

Work:

1. Run the read-only mode and review its result with the operator.
2. Run the transfer once.
3. Record the plan digest, the per-group readback and the remote screenshot IDs in a dated note under `docs/notes/`.

Acceptance:

- The final read passes for every declared group, and the preserved sets are unchanged.
- No review submission happens.
- A failed readback is recorded as a failure, with no retry under the same approval record.
