# Guarded Screenshot Transfer

## Status and scope

This specification answers [issue #28](https://github.com/AndrewDongminYoo/app-store-assets/issues/28), "Build the guarded screenshot transfer adapter".
The operator approved the plan on 2026-10-14.
It defines the contract only; this change adds no code, and [the implementation plan](../plans/2026-10-14-guarded-screenshot-transfer.md) splits the code into separate pull requests.

The adapter transfers App Store screenshots for one Apple target from a reviewed offline plan.
It covers iOS screenshot sets only, because `make_plan` already rejects macOS image operations.
Google Play images, App Previews, metadata text, binaries and review submission are out of scope.

The adapter adds no service, database or capture abstraction.
It does not change how images are captured, composed or prepared.

## Terms

- **Plan**: the record that `make_plan` in `app_store_assets/planning.py` returns for operation `images`, as `{"payload": ..., "digest": ...}`.
- **Target**: the plan's `target` identity (`store`, `platform`, `account`, optional `account_id`, `app_id`, `flavor`, `stage`, `version`).
  For Apple, `app_id` is the bundle identifier.
- **Slot**: a catalog display class name, such as `APP_IPHONE_65`, as `catalog/store-rules-v1.json` lists it.
- **Placement group**: all screenshots of one locale in one slot, in order.
  The plan's `listing.images[locale][slot]` is the intended group; App Store Connect's screenshot set for that localization and display type is the remote group.
- **Supplied snapshot**: the `metadata-snapshot` record that the target's `remote` path supplies, as `remote_observation` reduces it into the plan's `remote` field.
- **Approval record**: the separate record that this specification defines in [Approval record](#approval-record).

## Architecture

The transport is Ruby Spaceship from fastlane 2.240.1, inside `lib/fastlane_assets.rb`.
Python's standard library has no ES256 signing, so the App Store Connect API token cannot be made in the Python package without a new dependency.

The responsibilities split as follows:

1. Python (`app_store_assets`) keeps the offline contract.
   It re-derives the plan, validates the approval record, and returns the verified intent as JSON.
   It constructs no provider and makes no network call.
2. Ruby (`lib/fastlane_assets.rb`) receives that verified intent from a local Python process, as `prepare_local` already does with `Open3`.
   It reads the remote state, compares it, and makes the writes through Spaceship.
3. The legacy `AppStoreAssets.prepare` entrypoint stays blocked.
   The new entrypoint is a separate method that requires a plan path and an approval record path.

Spaceship loads only inside the new entrypoint.
Loading `lib/fastlane_assets.rb` and running `ruby -c lib/fastlane_assets.rb` must keep working on a machine that does not have the fastlane gem.

## Plan and approval

The offline plan type does not change.
Its payload keeps `type: offline-release-plan`, `executable: false` and `effects: []`, and `verify_plan` keeps rejecting any other value.
The adapter never edits a plan, and a plan never becomes executable by itself.

### Approval record

Execution authority comes from a separate approval record that the operator writes for one plan.
It binds the plan digest to the exact target and operation:

```json
{
  "schema_version": 1,
  "type": "transfer-approval",
  "plan_digest": "<plan digest>",
  "target": {
    "store": "apple",
    "account": "<target account>",
    "app_id": "<bundle identifier>",
    "platform": "ios",
    "version": { "name": "<version name>", "build": "<build>" }
  },
  "operation": "images"
}
```

Validation follows the existing exact-key rules (`exact_keys` in `app_store_assets/contracts.py`):

- Unknown keys, missing keys and wrong value types fail.
- `plan_digest` must equal the plan's `digest` after `verify_plan` succeeds.
- Every `target` field must equal the same field of the plan's `target`.
  When the plan's target has `account_id`, the approval record must contain the same `account_id`.
- `operation` must be `images` and must equal the plan's `operation`.
- The record contains no credential, key path, token or other secret.

The approval record is not one of the plan's inputs, because the plan digest would then depend on its own approval.
It is supplied to the entrypoint by path and read with the same no-follow, private-name checks as other inputs (`safe_path` in `app_store_assets/records.py`).

One approval record authorizes one execution attempt.
No database records its use.
Instead, a repeated run fails at the [live readback](#live-remote-readback): after any upload or deletion, the remote state differs from the supplied snapshot.
A retry after a partial failure therefore needs a new snapshot, a new plan and a new approval record.

## Pre-execution checks

All checks in this section run before the first write.
A failed check stops the run with no remote change.

### Re-derivation

Immediately before execution, `verify_plan(root, plan)` runs again.
It re-derives the plan from the current inputs with `make_plan` and requires the result to be equal to the supplied plan, digest included.
A changed profile, listing, image byte, snapshot, runtime or catalog therefore fails in the Python verification that the Ruby entrypoint calls first, before Spaceship loads and before any remote call.
The approval record validation then runs against the verified plan.

### Live remote readback

Today an Apple image plan accepts the supplied snapshot with `remote_evidence: supplied-snapshot-freshness-unverified`.
The adapter closes that gap: after the Python checks pass, it reads the remote state live through Spaceship, read-only, and compares it with the plan's `remote` field.

The live read covers:

- The app found by the target's bundle identifier, and the App Store version for the target's platform and version name.
- The version's ID, which must equal the snapshot's `version_id`.
  This equality also confirms that the authenticated session reaches the app and version that the snapshot was taken from.
- The version state, which must still be editable with no active review, as `validate_apple_localizations` requires of the snapshot.
- For each locale in `replacement.locales`, the screenshot set (`AppScreenshotSet.all`) of each slot in `replacement.slots`, with the screenshots of each set in their current order.
- For each locale in `replacement.locales`, the ordered screenshot IDs of every other display class.
  This is a read-only baseline for the [post-transfer checks](#post-transfer-checks); it is not compared with the snapshot.

For each declared placement group, the live group must match the snapshot group in every field that the snapshot records.
After `remote_observation`, those fields are the ordered screenshot `id` values and, where present, `source_sha256`, `provider_sha256`, `processing_state`, `width`, `height` and `size`.
The implementation defines and tests the mapping from each of these fields to a Spaceship 2.240.1 value, for example `processing_state` to `asset_delivery_state`.
A snapshot field that has no defined Spaceship equivalent fails the comparison; it is never skipped.
A declared group that exists on one side only is a difference.
Any difference stops the run before a write; the adapter reports the differing groups and does not try to merge them.

## Placement-group comparison

The unit of comparison and of change is the complete placement group, never a single file.
`make_plan` already requires `replacement.locales` and `replacement.slots` to equal the listing's groups exactly.

For each declared group, the adapter decides one action:

| Remote group (live, matched to the snapshot)                                        | `allow_delete` | Action                                                        |
| ----------------------------------------------------------------------------------- | -------------- | ------------------------------------------------------------- |
| Same count, and the `source_file_checksum` values equal the planned MD5s in order   | any            | No change.                                                    |
| Empty or absent                                                                     | any            | Upload the planned group.                                     |
| Not empty and different                                                             | `true`         | Delete the remote screenshots, then upload the planned group. |
| Not empty and different                                                             | `false`        | Refuse the whole run before any write.                        |

The adapter decides the action of every group before it changes any group.
A refusal in one group therefore prevents writes in all groups.

Deletion happens only when `replacement.allow_delete` is `true`, and only in a group whose locale is in `replacement.locales` and whose slot is in `replacement.slots`.
A display class that the plan does not declare is never read for a write, never deleted and never reordered, also in a declared locale.
A locale that the plan does not declare is never touched.

Delete-then-upload leaves a group empty for a short time.
This is acceptable because the selected version must be editable with no active review, so the group is not visible on the App Store during the transfer.

## Transfer and readback

### Byte binding

The plan binds each image by the SHA-256 of its final bytes.
App Store Connect reports `source_file_checksum`, which is the MD5 of the uploaded file, so the plan does not contain the value that the readback compares.

For each planned image, the adapter reads the bytes once, checks their SHA-256 against the plan, and writes them to a private temporary file.
It computes the expected MD5 from those same bytes and uploads that temporary file.
It never computes the MD5 from, or uploads, a second read of the source path.

### Upload order

The adapter uploads each group's images in plan order with `upload_screenshot(path:, wait_for_processing:, position:)`.
Each call gives an explicit position that is derived from the image's index in the planned group.
The value of `wait_for_processing:` does not replace the adapter's own [bounded processing readback](#bounded-processing-readback); that readback is the gate.
The implementation confirms Spaceship 2.240.1's position convention from its source before it relies on it, and records the result in its tests.

### Bounded processing readback

App Store Connect can report the checksum and the processing state late, directly after an upload.
The QuestKeeper precedent shows the failure: deliver's deduplication keyed on a checksum that was not ready, which produced 10 − N duplicates and a vacuous "Successfully uploaded" line.
So a returned upload call is not evidence of a correct group.

After the uploads of a group, the adapter polls the group's screenshot set until one of these occurs:

- Every screenshot is `complete?` and has a non-empty `source_file_checksum`: the poll ends and the readback starts.
- A screenshot is `error?`: the run fails and reports its `error_messages`.
- The poll limit is reached: the run fails as not confirmed.

The default poll interval is 5 seconds and the default limit is 600 seconds per group.
Both are parameters of the entrypoint with upper bounds; there is no unbounded wait.

The readback then requires all of these for the group:

- The count equals the planned count.
- The ordered `source_file_checksum` values equal the ordered planned MD5 values.
- Every screenshot is still `complete?`.

When only the order differs, the adapter calls `reorder_screenshots(app_screenshot_ids:)` once with the planned order and reads the group again.
Any other mismatch, or a mismatch after that reorder, is a failure.
A readback that does not match is never reported as a success.

### Post-transfer checks

After all declared groups pass the readback, the adapter reads the screenshot sets of the declared locales again.
Every display class that the plan does not declare must have the same ordered screenshot IDs as in the pre-execution live read.
A difference is reported as a failure, even though the adapter did not request it.

### Result

The entrypoint prints one JSON result to standard output: the plan digest, the target, and for each declared group the action, the readback result and the remote screenshot IDs.
It writes no file into the repository and no record into a store of its own.
It exits non-zero on any failure, also after writes have started; the result then names the groups that changed before the failure.

## Provenance

Asset provenance stays `unverified-import`.
Transfer is not capture evidence, so the adapter never promotes provenance and never writes a capture-time build claim.

## Credentials

Authentication uses Spaceship's existing login, an App Store Connect API key or an Apple ID session, configured by the operator outside this repository.
The personal metadata lanes log in today with an Apple ID (`FASTLANE_APPLE_ID`); which method the first authorized run uses is the operator's choice, and the adapter works with either.
No key material, key path or token is stored in this repository, in a plan, in an approval record or in the result.
`app_store_assets/records.py` already rejects private credential inputs, such as `.p8` files, from the public inventory, and the new inputs keep that check.

## Verification

All automated verification uses a fake App Store Connect.
The fake replaces the Spaceship objects that the adapter calls, with in-memory screenshot sets whose checksum and processing state can be made late, wrong or failed.
The default test command must not need the fastlane gem, network access or credentials.

The fake must be able to produce each state that a guard exists for:

- A live group that differs from the snapshot.
- A non-empty group with `allow_delete: false`.
- A processing state that is late, that errors, or that never completes.
- A checksum that is empty at first, then different from the planned MD5.
- An order that differs after upload.
- An undeclared display class that changes during the run.

Each guard's test must fail when the guard is removed.

A real upload, placement deletion or review submission needs explicit operator authorization for the target app and operation, as `AGENTS.md` requires.
It is out of scope for every implementation unit except the final authorized smoke run.

## Sources

- Spaceship 2.240.1 [`app_screenshot_set.rb`](https://github.com/fastlane/fastlane/blob/2.240.1/spaceship/lib/spaceship/connect_api/models/app_screenshot_set.rb): `AppScreenshotSet.all`, `.get`, `#upload_screenshot(path:, wait_for_processing:, position:)`, `#reorder_screenshots(app_screenshot_ids:)`, `#delete!`.
- Spaceship 2.240.1 [`app_screenshot.rb`](https://github.com/fastlane/fastlane/blob/2.240.1/spaceship/lib/spaceship/connect_api/models/app_screenshot.rb): `source_file_checksum`, `asset_delivery_state`, `complete?`, `error?`, `error_messages`, `delete!`.
- The closed pull request #3 branch (`9fc5395`) has no screenshot transport code; its `provider_ruby.py` is a Ruby file-loading shim.
- QuestKeeper store-asset precedent: `/Users/dongminyu/Development/01_personal/llm-wiki-dongminyu/wiki/sources/claude--projects---users-dongminyu-development-01-personal-quest-keeper--memory--store-assets-pipeline.md`, as [the first-stage contract](screenshot-bundles.md#sources) cites it.
- Current contracts: `app_store_assets/planning.py` (`make_plan`, `verify_plan`), `app_store_assets/metadata.py` (`remote_observation`), `app_store_assets/catalog.py` (`validate_apple_localizations`), `app_store_assets/records.py` (credential input rejection).
