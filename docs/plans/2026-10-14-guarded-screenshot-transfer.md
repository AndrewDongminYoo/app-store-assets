# Guarded Screenshot Transfer Plan

Operator-approved plan, 2026-10-14, for [issue #28](https://github.com/AndrewDongminYoo/app-store-assets/issues/28).
[The specification](../specs/2026-10-14-guarded-screenshot-transfer.md) owns the contract; this plan owns only the order of work and the acceptance of each unit.

## Decisions

- Scope of the first pull request: the specification and this plan only, with no code.
- Transport: Ruby Spaceship from fastlane 2.240.1, inside `lib/fastlane_assets.rb`.
- First target app for offline-profile v1: kkomkkomi.

## Rules for every unit

- Each unit is a separate pull request, in the order below.
  A unit starts only after the previous unit has merged.
- `python3 -m unittest discover -s tests -v` and `ruby -c lib/fastlane_assets.rb` pass at every unit.
  The default suite needs no fastlane gem, no network and no credentials.
- No unit except U5 makes a real App Store Connect call.
  Tests use the fake App Store Connect that [the specification's verification section](../specs/2026-10-14-guarded-screenshot-transfer.md#verification) defines.
- Each new guard has a test that fails when the guard is removed.
- No unit adds a service, a database, a capture abstraction or a Python dependency.

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
2. Add a read-only verification function and command: run `verify_plan`, then validate the approval record against the verified plan, then print the verified intent as JSON.
3. Add the record's structural summary to `schemas/` and keep the Python validator authoritative.

Acceptance:

- A changed plan input, a different `plan_digest`, a different target field, a missing `account_id` when the plan has one, a different operation, an unknown key and a credential-shaped path each fail with a distinct error.
- The plan payload type, `executable: false` and `effects: []` are unchanged.
- The `app_store_assets` reader package still constructs no provider.

## U3: Spaceship read-only readback and snapshot comparison

Repository: app-store-assets (Ruby entrypoint, tests driven from Python as `tests/test_bridge.py` does).

Work:

1. Add the new Ruby entrypoint with a read-only mode.
   It calls the U2 command through `Open3`, then reads the app, the version, the version's attached build, the localizations of the declared locales and the declared screenshot sets through Spaceship.
   The attached build's number must equal `target.version.build`, as [the specification's live remote readback](../specs/2026-10-14-guarded-screenshot-transfer.md#live-remote-readback) defines.
2. Load Spaceship only inside the entrypoint, so loading `lib/fastlane_assets.rb` works without the fastlane gem.
3. Compare each declared placement group with the plan's `remote` field and print the per-group result as JSON.
   Define and test the mapping of each snapshot field to a Spaceship value; a field with no mapping fails the comparison.
   Also record the ordered screenshot IDs of the preserved sets, as the baseline for U4 step 6.
4. Take the target's exclusive lock file before the live read and remove it at exit, as [the specification's approval record section](../specs/2026-10-14-guarded-screenshot-transfer.md#approval-record) defines.
5. Add the fake App Store Connect to the tests, in place of the Spaceship objects that the entrypoint calls.

Acceptance:

- A different `version_id`, a version that is not editable or has an active review, an attached build that differs from the approved build or is missing while the version name and `version_id` stay the same, a changed screenshot ID, a changed order and a group present on one side only each refuse, with the differing groups named.
- An existing lock file for the target refuses before any Spaceship call.
- The read-only mode makes no write call on the fake; the test asserts the fake's call log.
- `AppStoreAssets.prepare` stays blocked.

## U4: Transfer executor

Repository: app-store-assets (Ruby entrypoint, fake-tested).

Work:

1. Decide every group's action before any write, as the [placement-group comparison](../specs/2026-10-14-guarded-screenshot-transfer.md#placement-group-comparison) defines.
2. For a declared group with no remote set, create the set with `create_app_screenshot_set` on the declared locale's localization and the declared slot only, as [the specification's absent-set creation](../specs/2026-10-14-guarded-screenshot-transfer.md#absent-set-creation) defines.
3. Bind bytes: check SHA-256 against the plan, write a private temporary copy, compute MD5 from the same bytes, upload the copy.
4. Upload with explicit positions, after confirming Spaceship 2.240.1's position convention from its source.
5. Poll with the bounded interval and limit, then read back count, checksum order and processing state; reorder once when only the order differs.
6. Read the declared locales again: every declared group still passes its readback, the preserved sets are unchanged, and no other set exists.

Acceptance:

- With the fake, every state in [the specification's verification list](../specs/2026-10-14-guarded-screenshot-transfer.md#verification) produces the outcome that the specification defines for it.
  Each state that the specification defines as a failure produces a non-zero exit and a result that names the failing group.
- A processing state or checksum that is late but becomes correct within the limit passes; one that stays incomplete or empty fails at the limit.
- An order that differs only after upload passes after exactly one `reorder_screenshots` call; an order that still differs after that call fails.
- `allow_delete: false` with a non-empty, different group refuses before the first write, also when an earlier group would only upload.
- A build or version state that changes during the run fails the post-transfer checks.
- A screenshot creation that keeps failing ends the upload call within the bounded `SPACESHIP_SCREENSHOT_UPLOAD_TIMEOUT`, and the previous value of that variable is restored.
- A matching group with an errored screenshot refuses before the first write; a matching group that is still processing passes only after its bounded readback, also before the first write.
- A declared group with no remote set passes after exactly one `create_app_screenshot_set` call on that locale's localization with that slot as `screenshotDisplayType`, followed by the upload into the new set.
- No set other than a declared group receives a delete, upload or reorder call, also a declared slot of a declared locale that the listing does not pair.
- No `create_app_screenshot_set` call is made for a display type or locale outside the declared groups, also a declared slot of a declared locale that the listing does not pair; the test asserts the fake's call log.
- Provenance stays `unverified-import`.

## U5: Authorized smoke upload for kkomkkomi

Repository: app-store-assets, run against the U1 kkomkkomi profile.

Preconditions:

- U1 to U4 have merged.
- The operator gives explicit authorization for kkomkkomi and for each operation of this run (upload, and deletion when `allow_delete` is `true`), as `AGENTS.md` requires.
- A fresh supplied snapshot, a fresh plan and a new approval record exist for this run.
- The operator declares an exclusive App Store Connect writer window for kkomkkomi for the whole run, as [the specification's approval record section](../specs/2026-10-14-guarded-screenshot-transfer.md#approval-record) defines: no other tool, machine, fastlane or deliver run, or App Store Connect web edit writes to its screenshots, selects a different build, or changes the version's state, including a review submission.

Work:

1. Run the read-only mode and review its result with the operator.
2. Run the transfer once.
3. Record the plan digest, the per-group readback and the remote screenshot IDs in a dated note under `docs/notes/`.

Acceptance:

- The readback matches for every declared group, and the preserved sets are unchanged.
- No review submission happens.
- A failed readback is recorded as a failure, with no retry under the same approval record.
