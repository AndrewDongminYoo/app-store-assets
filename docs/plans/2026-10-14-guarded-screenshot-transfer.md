# Guarded Screenshot Transfer Plan

Operator-approved plan, 2026-10-14, for [issue #28](https://github.com/AndrewDongminYoo/app-store-assets/issues/28).
[The specification](../specs/2026-10-14-guarded-screenshot-transfer.md) owns the contract as numbered invariants; this plan owns the order of work, the provider details, and the acceptance tests that hold each unit to those invariants.
As of 2026-10-15, U2 ([PR #38](https://github.com/AndrewDongminYoo/app-store-assets/pull/38)), U3 ([PR #39](https://github.com/AndrewDongminYoo/app-store-assets/pull/39)) and U4 ([PR #42](https://github.com/AndrewDongminYoo/app-store-assets/pull/42)) are merged.
U5 remains an unperformed, separately authorized smoke run; the implementation sections below describe the shipped entrypoints and helpers.

## Decisions

- Scope of the first pull request: the specification and this plan only, with no code.
- Transport: Ruby Spaceship from fastlane 2.240.1, with entrypoints in `lib/fastlane_assets.rb` and transfer helpers in `lib/fastlane_transfer.rb`.
- First target app for offline-profile v1: kkomkkomi.
- After the first draft (pull request #30) reached the review-loop round limit, the specification keeps only invariants, and step order and provider behavior live here as tests (operator decision, 2026-10-14).

## Rules for every unit

- Each unit is a separate pull request, in the order below, and starts only after the previous unit has merged.
- `python3 -m unittest discover -s tests -v` and `ruby -c lib/fastlane_assets.rb` pass at every unit; the default suite needs no fastlane gem, no network and no credentials.
  From U4, also run `ruby -c lib/fastlane_transfer.rb` for the separate transfer helpers.
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
| `APIClient#with_asc_retry` retries an HTTP 429 response with exponential backoff (1, 2, 4 … seconds) until the backoff exceeds 3600 seconds, independent of its 5-try budget for 500 and 504 ([`api_client.rb`](https://github.com/fastlane/fastlane/blob/2.240.1/spaceship/lib/spaceship/connect_api/api_client.rb)); `SPACESHIP_TIMEOUT` bounds only each HTTP attempt. | 6 | Wrap every provider call, reads included, in an adapter-level deadline (Ruby's `Timeout.timeout`, default 120 seconds per call, a parameter with an upper bound); reaching it fails the run. |

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
2. Add a verification command that makes no remote call: run `verify_plan`, validate the approval record against the verified plan, and for every planned image read the bytes once, check their SHA-256, and write those same bytes into a private staging directory that the run owns; then print the verified intent as JSON with each image's staged path, SHA-256 and MD5 (invariants 1 and 2).
   Ruby uploads only these staged files, so no byte crosses the process boundary that the Python check did not hash.
3. Add the record's structural summary to `schemas/` and keep the Python validator authoritative.

Acceptance:

- A changed plan input, a different `plan_digest`, a different target field, a missing `account_id` when the plan has one, a different operation, an unknown key and a credential-shaped path each fail with a distinct error.
- An image that changed after planning fails, whichever declared group it belongs to.
- Each staged file equals the bytes that were hashed, and a source replaced after staging does not change what the intent points at.
- The plan payload type, `executable: false` and `effects: []` are unchanged, and the reader package still constructs no provider.

### U2 command and owned paths

`python3 -B -m app_store_assets_local.transfer --root PROJECT --plan PLAN --approval APPROVAL --staging-dir DIRECTORY` owns approval validation and byte staging.
The implementation stays in the existing local-write extension so importing the read-only package does not import a writer.
`schemas/transfer-approval-v1.json` is the structural summary, and `tests/test_transfer_approval.py` exercises the command and guards with synthetic plans and images.
The README documents caller ownership of the staging directory.

The caller supplies an existing empty private directory outside the project and runtime, using an absolute path without symlinks or parent traversal.
The verifier checks the plan and approval before staging, opens the directory without following symlinks, and writes new private files through its descriptor.
It hashes each captured image before writing those bytes, checks the plan and approval captures again before returning, and refuses a replaced directory or changed staged file.
The stdout byte bound includes the exact JSON encoding and final newline.
Failed verification removes only files created by that run.
U3 owns directory lifetime and the target lock, and must keep both through the final read.

The JSON intent preserves the digest, target, mode, supplied remote observation, replacement policy and `unverified-import` provenance.
Its `groups` array contains only actual listing pairs, with each image's `staged_path`, `sha256` and `md5`.
The intent sets `remote_verified: false`; U3 still performs the live comparisons.

## U3: Read-only live readback

Repository: app-store-assets (Ruby entrypoint, tests driven from Python as `tests/test_bridge.py` does).

Work:

1. Add the new Ruby entrypoint with a read-only mode that loads Spaceship only inside it.
2. Take an exclusive lock file for the target's bundle identifier under the system temporary directory, with create-new semantics, before the U2 command and the live read, and remove it when the run ends; an existing lock refuses the run and is removed only by the operator.
   The entrypoint creates the U2 staging directory and passes it to the U2 command, so it owns that directory and removes it in an `ensure` on every exit.
3. Call the U2 command through `Open3`, then read the app, the version, its attached build, the localizations of the declared locales, the declared groups and the preserved sets.
4. Compare with the supplied snapshot (invariant 3), defining and testing the mapping of each snapshot field to a Spaceship value, and print the per-group result as JSON with provider output on standard error (invariant 8).
5. Add the fake App Store Connect to the tests.

Acceptance (fake states):

- A different `version_id`; a version that is not editable or has an active review; an attached build that differs from the approved one or is missing while the version name and ID stay the same; a changed screenshot ID or order; a group present on one side only; a snapshot field with no mapping: each refuses and names the group.
- An existing lock file refuses before any Spaceship call.
- The read-only mode makes no remote write; the test asserts the fake's call log.
- The staging directory is gone after a successful run and after a refused or failed one.
- A provider call that keeps returning HTTP 429 fails the run at the adapter's per-call deadline.
- `AppStoreAssets.prepare` stays blocked.

### U3 live mappings and entrypoint

`AppStoreAssets.transfer_screenshots(root:, target:, plan:, approval:, mode: "read-only", deadline: 120, verification_deadline: 120)` is the U3 entrypoint.
Its target must equal the whole U2-verified target before any provider read.
It reuses the U0 snapshot reader with a bounded provider-call wrapper; the default U0 reader and public export entrypoint retain their existing behavior.
The fastlane 2.240.1 source links in the provider table were rechecked for build reads, screenshot attributes, localization methods, and retry behavior during U3 implementation.

| Supplied observation | Live mapping |
| --- | --- |
| `schema_version`, `type` | The U0 reader's fixed public record envelope. |
| `target` | The U2-verified identity, bound to the bundle lookup, iOS version name, and attached build number; account, flavor and stage remain declarations. |
| `version_id` | `AppStoreVersion.id`. |
| `editable`, `review_active` | The U0 editable-state allowlist and the live in-progress review submission. |
| `binary` | Attached build number and processing state, with the approved app/platform/version identity. |
| `build_exists` | Whether the live version has an attached build. |
| `app_info_id`, `fields` | The U0 app-info and version-localization mappings. |
| `release_notes` | Each version localization's `whats_new` value. |
| Declared screenshot ID, order, processing state, width and height | The ordered set's `AppScreenshot.id`, `asset_delivery_state.state`, and `image_asset` dimensions. |

Every supplied non-image field is compared, and an absent live key is a refusal rather than an ignored observation.
Each declared image group must agree on set presence, screenshot count, IDs and order, and every supplied image annotation.
Screenshot IDs are required for a non-empty declared snapshot group.
An absent set and an existing empty set are distinct.
Other sets of the declared locales are retained as the preserved-set baseline.
Unmapped annotations such as `revision` or `binary.source_sha256` refuse the run.

The lock name uses SHA-256 of the bundle ID under the canonical `/tmp` directory, so another `TMPDIR` or project path cannot create a second lock namespace.
Create-new semantics refuse an existing lock before U2 or any provider read.
The run checks the lock inode before and after live reads.
Cleanup checks the owned inode, atomically renames the entry into a private sibling quarantine, and checks the captured inode before deletion.
A mismatch before rename leaves the entry in place; a mismatch after rename retains the quarantine and reports its path without restoring it over a possible new lock.
The private U2 staging directory is removed on success or failure unless external replacement prevents safe cleanup, in which case the run refuses and retains the entry for operator recovery.
This handles ordinary pathname replacement races; deliberate same-UID mutation inside the private quarantine after its final check is outside the guarantee because portable Ruby/POSIX has no atomic compare-and-unlink operation.

Each provider call and each Python verification has its own positive deadline capped at 600 seconds.
The Python bridge drains both pipes, limits each stream to 8 MiB, and kills its process group on failure or timeout.
The read-only result uses `action: "verify"` and `readback.snapshot_matches: true`; it makes no upload/replace decision and no processing-completion claim.
`tests/test_transfer_readback.py` exercises these rules through the real U2 process and the existing fake Spaceship, without a gem, credentials, or network.

## U4: Transfer mode

Repository: app-store-assets (Ruby entrypoint, fake-tested).

Work:

1. Add a transfer mode to the U3 entrypoint that keeps one lock from the U2 command through the final read.
2. Settle every check, every group's action and the health of every unchanged group before the first remote write (invariant 5).
3. Write only declared groups, following the [provider behaviors](#provider-behaviors): create absent sets, upload the U2 staged files with explicit positions after re-checking each staged file's SHA-256, and replace a group only under `allow_delete`.
4. Poll each group within the bound, read back count, MD5 order and processing, and reorder once when only the order differs.
5. Do the final read of invariant 7.

Acceptance (fake states, each with the outcome the specification's invariants require):

- A source image replaced after U2 staged it is never uploaded, and a staged file that no longer matches its SHA-256 refuses before the first write.
- A non-empty, different group with `allow_delete: false` refuses before the first write, also when an earlier group would only upload.
- A matching group with an errored screenshot refuses before the first write; a matching group that is still processing passes only after its bounded poll, before the first write.
- A declared group with no remote set passes after exactly one `create_app_screenshot_set` call on its localization with its slot, then the upload into the new set.
- During upload readback, a processing state or checksum that is late but correct within the bound passes; processing errors fail immediately, and incomplete processing or missing checksums fail at the bound.
- A checksum that differs from the planned MD5 fails; an order that differs only after upload passes after exactly one `reorder_screenshots` call and fails if it still differs.
- A placeholder creation that keeps failing, and a successful creation followed by upload requests that time out, each end within the configured bounds and restore both environment variables.
- A preserved set, a declared group after its own readback, or the attached build or version state that changes during the run fails the final read.
- No create, upload, delete or reorder call reaches a preserved set, an undeclared locale, or a declared slot of a declared locale that the listing does not pair; the test asserts the fake's call log.
- A provider call that prints to standard output leaves exactly one JSON document on standard output.
- A create, upload, delete or reorder call that keeps returning HTTP 429 fails the run at the per-call deadline, and the staging directory and the lock are removed.
- Provenance stays `unverified-import`.

### U4 implementation and verification

`lib/fastlane_assets.rb` owns the entrypoint, U2 boundary and lock; `lib/fastlane_transfer.rb` contains the transfer helpers loaded by that entrypoint.
The snapshot reader optionally retains the provider localization and set objects for the transfer, without changing the U0 public snapshot schema or its default behavior.
Transfer mode uses these objects only for actual listing pairs.
The preserved-set baseline includes set IDs, screenshot IDs, order, checksums, processing and dimensions, and final readback compares it exactly.
Final declared-group reads must also match their own completed readbacks, including IDs, and the final build ID and version state must equal the initial live read.

Before deciding actions, the adapter checks all staged paths and hashes.
It also validates all declared localization and existing set resource IDs before any write.
Missing source checksums on an existing group are settled before choosing its action, retaining its initial screenshot IDs throughout that poll.
When deletion is authorized, a confirmed `AWAITING_UPLOAD` placeholder may remain without a checksum and proceed to replacement; other missing checksums still wait, and failed processing or changed IDs still refuses the whole run.
This recovers an abandoned placeholder under a newly approved retry and the exclusive writer window; Fastlane creates the placeholder before uploading bytes and patching its checksum.
Checksum resolution and an unchanged group's processing poll share one preflight group deadline.
It checks all staged files again after unchanged groups finish polling, and checks each image immediately before upload.
The staging directory remains private for the entire run; as with the U3 ownership contract, deliberate same-UID mutation inside that directory is outside portable pathname isolation guarantees.
The source image paths are never read by the Ruby uploader.
All write calls mark the group as possibly changed before entering the provider, because a timeout can follow a successful server-side write.
That group list survives provider, final-read and cleanup errors.

`group_deadline` bounds the complete write and polling sequence for a changed group, or the preflight poll for an unchanged group.
Each provider operation uses the smaller of the remaining group time and the per-call `deadline`.
Polling uses a monotonic clock and sleeps no longer than the remaining time.
The environment bounds and provider-output redirection are restored with `ensure`.
`tests/test_transfer_execution.py` uses the real U2 verifier and the opt-in `tests/fake_spaceship/transfer.rb` writer; the existing snapshot fake still rejects writes unless explicitly opted into this fixture.
The fastlane 2.240.1 upload, delete, create, read and reorder signatures were checked against the pinned source before implementation.

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

## Reconciliation 2026-10-14: U0 and the U1 runtime pin

The operator made two decisions on 2026-10-14 while starting U1.
This section adds to the steps above and does not rewrite them; for U0, the shipped `AppStoreAssets.export_snapshot` in `lib/fastlane_assets.rb` and its tests in `tests/test_snapshot_export.py` are the authority.

1. The U1 profile's runtime is a git submodule of app-store-assets inside kkomkkomi, pinned at a `main` commit.
   The current profile contract already requires `runtime.path` to be a clean checkout inside the consumer root, so the contract does not change.
2. A U1 plan needs a supplied `metadata-snapshot` of the real App Store Connect state, but no command produced one and U1 makes no store call.
   A new unit, U0, adds a read-only snapshot export, and the operator runs it once for kkomkkomi with their own login before U1 finishes.

Effect on the units:

- U0 precedes U1.
- U0 lives in app-store-assets: `AppStoreAssets.export_snapshot(target:, output:)` makes read calls only and writes one `metadata-snapshot` record that passes `validate_public_metadata` and `remote_observation`.
  Its tests use the fake App Store Connect, as the rules for every unit require; only the operator's own run reaches App Store Connect, with read calls only.
- U1 now also adds the app-store-assets submodule to kkomkkomi and a kkomkkomi lane that authenticates Spaceship and calls `export_snapshot`.

Lines above that these decisions supersede:

- U1 step 3, "Keep the existing file and lanes unchanged", and the U1 acceptance line "no change to the kkomkkomi Fastfile lanes": the new export lane is now in U1's scope, and the existing lanes stay unchanged.
  The plan could not supply a snapshot without a lane that reads App Store Connect, and the lane belongs to the consumer, not to app-store-assets.
- The rule "No unit except U5 makes a real App Store Connect call" and the U1 acceptance line "No store call, no credential": they still hold for every pull request's code and verification, which use the fake.
  The operator's one read-only export run for kkomkkomi is the single exception; it happens outside any pull request's verification, with the operator's own login, and makes no remote write.
