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
- **Declared group**: a placement group whose locale and slot pair is a key pair of the plan's `listing.images`.
  `make_plan` compares `replacement.locales` and `replacement.slots` with the listing only as separate sets, so a pair of a declared locale and a declared slot that the listing does not contain is not a declared group.
- **Preserved set**: every other screenshot set of a declared locale, whatever its display class.
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
    "flavor": "<flavor>",
    "stage": "<stage>",
    "version": { "name": "<version name>", "build": "<build>" }
  },
  "operation": "images"
}
```

Validation follows the existing exact-key rules (`exact_keys` in `app_store_assets/contracts.py`):

- Unknown keys, missing keys and wrong value types fail.
- `plan_digest` must equal the plan's `digest` after `verify_plan` succeeds.
- `target` passes the same identity validation as a plan target (`target_identity` in `app_store_assets/contracts.py`), which requires `flavor` and `stage` for Apple too, and it must equal the plan's whole `target`.
  So when the plan's target has `account_id`, the approval record must contain the same `account_id`, and when it has none, the record must have none.
- `operation` must be `images` and must equal the plan's `operation`.
- The record contains no credential, key path, token or other secret.

The approval record is not one of the plan's inputs, because the plan digest would then depend on its own approval.
It is supplied to the entrypoint by path and read with the same no-follow, private-name checks as other inputs (`safe_path` in `app_store_assets/records.py`).

An approval record authorizes a run only while the live remote state still equals the supplied snapshot.
No database records its use, so the record itself does not prevent a second run.
A second run with the same record is refused at the [live readback](#live-remote-readback) once any upload or deletion has changed the remote state; a run that made no remote change can be repeated, and it then repeats the same checks against the same state.
A retry after a partial failure therefore needs a new snapshot, a new plan and a new approval record.

No other writer may change the target's screenshots during a run, because App Store Connect has no conditional write: the adapter cannot make a delete or an upload depend on the state that its live readback saw.
A run therefore requires an exclusive App Store Connect writer window for the target, which the operator declares before the run.
The window lasts from the live readback to the end of the [post-transfer checks](#post-transfer-checks).
In it, no other tool, machine, fastlane or deliver run, or App Store Connect web edit writes to the target's screenshots, selects a different build for the version, or changes the version's state, including a review submission.
The adapter cannot verify the window; it is an operator precondition, like the authorization that `AGENTS.md` requires.

Two runs for the same target on the same machine must not overlap, because both could pass the live readback before either writes.
The entrypoint creates an exclusive lock file for the target's bundle identifier under the system temporary directory, with create-new semantics, before the live readback, and removes it when the run ends.
An existing lock file refuses the run; a lock that a crashed run left behind is removed by the operator, never automatically.
The lock prevents only an overlapping run on the same machine, and it does not replace the writer window.

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
- The build attached to that version (`AppStoreVersion#get_build`), whose build number (`Build#version`) must equal `target.version.build`.
  When the snapshot records a `binary`, `validate_public_metadata` already requires its `version` to equal the target's version, so the same build number binds the snapshot too.
  The version name and `version_id` do not change when a different build is selected, so neither of those checks detects a build change after approval.
  A missing build or a different build number stops the run before any write.
- The version state, which must still be editable with no active review, as `validate_apple_localizations` requires of the snapshot.
- The version localization (`AppStoreVersionLocalization`) of each declared locale.
- The screenshot set (`AppScreenshotSet.all`) of each declared group, with its screenshots in their current order.
- The ordered screenshot IDs of every preserved set.
  This is a read-only baseline for the [post-transfer checks](#post-transfer-checks); it is not compared with the snapshot.

For each declared placement group, the live group must match the snapshot group in every field that the snapshot records.
After `remote_observation`, those fields are the ordered screenshot `id` values and, where present, `source_sha256`, `provider_sha256`, `processing_state`, `width`, `height` and `size`.
The implementation defines and tests the mapping from each of these fields to a Spaceship 2.240.1 value, for example `processing_state` to `asset_delivery_state`.
A snapshot field that has no defined Spaceship equivalent fails the comparison; it is never skipped.
A declared group that exists on one side only is a difference.
Any difference stops the run before a write; the adapter reports the differing groups and does not try to merge them.

## Placement-group comparison

The unit of comparison and of change is the complete placement group, never a single file.
`make_plan` already requires `replacement.locales` and `replacement.slots` to equal the listing's locales and slots as sets; the adapter acts on the declared groups, the listing's actual locale and slot pairs, only.

For each declared group, the adapter decides one action:

| Remote group (live, matched to the snapshot)                                        | `allow_delete` | Action                                                                         |
| ----------------------------------------------------------------------------------- | -------------- | ------------------------------------------------------------------------------ |
| Same count, and the `source_file_checksum` values equal the planned MD5s in order   | any            | No change.                                                                     |
| Set exists and is empty                                                             | any            | Upload the planned group into that set.                                        |
| Set absent                                                                          | any            | [Create the set](#absent-set-creation), then upload the planned group into it. |
| Not empty and different                                                             | `true`         | Delete the remote screenshots, then upload the planned group.                  |
| Not empty and different                                                             | `false`        | Refuse the whole run before any write.                                         |

The adapter decides the action of every group before it changes any group.
A refusal in one group therefore prevents writes in all groups.

A "No change" group must also be healthy before the first write: every screenshot has a non-empty `source_file_checksum` and is `complete?`.
A group that is still processing gets the same [bounded processing readback](#bounded-processing-readback) before the first write, and it becomes "No change" only when that readback passes.
A screenshot that is `error?`, or a poll that reaches its limit, refuses the whole run before any write.

### Absent-set creation

`upload_screenshot` is a method of an existing `AppScreenshotSet`, so a declared group with no remote set needs the set first.
The adapter creates it with `AppStoreVersionLocalization#create_app_screenshot_set(attributes: { screenshotDisplayType: <slot> })` on the localization of the declared locale, as deliver 2.240.1 does in `deliver/lib/deliver/app_screenshot_iterator.rb`.
The display type is the declared slot only, and the localization is the one that the live read found for the declared locale; a declared locale with no live localization refuses the run before any write.
The adapter creates a set only for a declared group whose action is "Set absent", and only after the actions of all groups are decided.
It never creates a set for a preserved set, for an undeclared locale, or for a declared slot of a declared locale that the listing does not pair.

Deletion happens only when `replacement.allow_delete` is `true`, and only in a declared group.
A preserved set is never written, deleted or reordered, also when its display class is declared for another locale.
A locale that the plan does not declare is never touched.

Delete-then-upload leaves a group empty for a short time.
This is acceptable because the selected version must be editable with no active review, so the group is not visible on the App Store during the transfer.

## Transfer and readback

### Byte binding

The plan binds each image by the SHA-256 of its final bytes.
App Store Connect reports `source_file_checksum`, which is the MD5 of the uploaded file, so the plan does not contain the value that the readback compares.

Before the first remote write, the adapter stages every planned image of every declared group whose action uploads: it reads the bytes once, checks their SHA-256 against the plan, and writes them to a private temporary file.
A missing, unreadable or mismatching image in any group refuses the whole run before any write, so a late group cannot fail after earlier groups changed.
It computes the expected MD5 from those same bytes and uploads that temporary file.
It never computes the MD5 from, or uploads, a second read of the source path.

### Upload order

The adapter uploads each group's images in plan order with `upload_screenshot(path:, wait_for_processing: false, position:)`.
Each call gives an explicit position that is derived from the image's index in the planned group.
The adapter always passes `wait_for_processing: false`.
Spaceship 2.240.1 defaults it to `true`, and then `AppScreenshot.create` in `app_screenshot.rb` polls every 2 seconds until the screenshot is `complete?` or `error?`, with no deadline.
With the default, the adapter would block inside Spaceship before its own [bounded processing readback](#bounded-processing-readback) starts; that readback is the gate.
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

The upload call itself must be bounded too.
When placeholder creation fails, `AppScreenshot.create` in Spaceship 2.240.1 catches the error and retries every 30 seconds until `SPACESHIP_SCREENSHOT_UPLOAD_TIMEOUT` minutes have passed (default 20), and it does not cap a value from the environment.
So while provider calls run, the entrypoint sets `SPACESHIP_SCREENSHOT_UPLOAD_TIMEOUT` to the group limit in whole minutes, rounded up and at least 1, and restores the previous value in an `ensure`.
One upload call can then wait at most that many minutes plus one 30-second retry interval, and a creation that still fails fails the run.

The readback then requires all of these for the group:

- The count equals the planned count.
- The ordered `source_file_checksum` values equal the ordered planned MD5 values.
- Every screenshot is still `complete?`.

When only the order differs, the adapter calls `reorder_screenshots(app_screenshot_ids:)` once with the planned order and reads the group again.
Any other mismatch, or a mismatch after that reorder, is a failure.
A readback that does not match is never reported as a success.

### Post-transfer checks

After all declared groups pass the readback, the adapter reads the version and the screenshot sets of the declared locales again.
The version's attached build number must still equal `target.version.build`, and the version must still be editable with no active review, as the [live remote readback](#live-remote-readback) required before the first write.
Every declared group must still pass the [readback requirements](#bounded-processing-readback) (count, ordered `source_file_checksum` values, `complete?`), because a writer that breaks the writer window can change a group after its own readback while later groups transfer.
Every preserved set must have the same ordered screenshot IDs as in the pre-execution live read.
A declared locale must have no screenshot set other than its declared groups and the preserved sets of the pre-execution live read.
A difference is reported as a failure, even though the adapter did not request it.

These checks detect only a change that is still visible in the final state.
A concurrent edit to a declared group that the transfer then deletes or replaces leaves no trace, because the final state then equals the plan; the checks cannot detect it, and only the [writer window](#approval-record) prevents it.

### Result

The entrypoint prints one JSON result to standard output: the plan digest, the target, and for each declared group the action, the readback result and the remote screenshot IDs.
Standard output contains only that JSON document.
Spaceship 2.240.1 writes status lines with `puts`: `AppScreenshot.create` in `app_screenshot.rb` writes one on each retry after a screenshot creation fails, and other calls write them when `Spaceship::Globals.verbose?` is set.
So the entrypoint sends Ruby's standard output to standard error while provider calls run (for example `$stdout = $stderr`, restored in an `ensure`), and it writes the JSON result to the original standard output.
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
- A version whose attached build differs from the approved build, or that has no attached build, while its name and `version_id` stay the same.
- A non-empty group with `allow_delete: false`.
- A group whose checksums match the plan while a screenshot is still processing or has errored, so that it is not yet a healthy "No change" group.
- A declared group whose remote set is absent, so that the adapter must create the set before the upload.
- A processing state that is late, that errors, or that never completes.
- A checksum that is empty at first, then different from the planned MD5.
- An order that differs after upload.
- A preserved set that changes during the run, including a declared slot of a declared locale that the listing does not pair.
- A declared group that changes after its own readback while a later group transfers.
- A version whose attached build or state changes during the run.
- An image of a later group whose bytes change or disappear after the Python verification.
- A screenshot creation that keeps failing, so that the upload call must end within the bounded `SPACESHIP_SCREENSHOT_UPLOAD_TIMEOUT`.
- A lock file that already exists for the target.
- A provider call that writes to standard output; the entrypoint's standard output must still parse as exactly one JSON document.

Each guard's test must fail when the guard is removed.

A real upload, placement deletion or review submission needs explicit operator authorization for the target app and operation, as `AGENTS.md` requires.
It is out of scope for every implementation unit except the final authorized smoke run.

## Sources

- Spaceship 2.240.1 [`app_screenshot_set.rb`](https://github.com/fastlane/fastlane/blob/2.240.1/spaceship/lib/spaceship/connect_api/models/app_screenshot_set.rb): `AppScreenshotSet.all`, `.get`, `#upload_screenshot(path:, wait_for_processing:, position:)`, `#reorder_screenshots(app_screenshot_ids:)`, `#delete!`.
- Spaceship 2.240.1 [`app_screenshot.rb`](https://github.com/fastlane/fastlane/blob/2.240.1/spaceship/lib/spaceship/connect_api/models/app_screenshot.rb): `source_file_checksum`, `asset_delivery_state`, `complete?`, `error?`, `error_messages`, `delete!`.
- Spaceship 2.240.1 [`app_store_version_localization.rb`](https://github.com/fastlane/fastlane/blob/2.240.1/spaceship/lib/spaceship/connect_api/models/app_store_version_localization.rb): `#create_app_screenshot_set(client:, attributes:)`; deliver 2.240.1 [`app_screenshot_iterator.rb`](https://github.com/fastlane/fastlane/blob/2.240.1/deliver/lib/deliver/app_screenshot_iterator.rb) calls it with `screenshotDisplayType` when a set is missing.
- Spaceship 2.240.1 [`app_store_version.rb`](https://github.com/fastlane/fastlane/blob/2.240.1/spaceship/lib/spaceship/connect_api/models/app_store_version.rb): `#get_build`; [`build.rb`](https://github.com/fastlane/fastlane/blob/2.240.1/spaceship/lib/spaceship/connect_api/models/build.rb): `version`, the build number.
- The closed pull request #3 branch (`9fc5395`) has no screenshot transport code; its `provider_ruby.py` is a Ruby file-loading shim.
- QuestKeeper store-asset precedent: `/Users/dongminyu/Development/01_personal/llm-wiki-dongminyu/wiki/sources/claude--projects---users-dongminyu-development-01-personal-quest-keeper--memory--store-assets-pipeline.md`, as [the first-stage contract](screenshot-bundles.md#sources) cites it.
- Current contracts: `app_store_assets/planning.py` (`make_plan`, `verify_plan`), `app_store_assets/metadata.py` (`remote_observation`), `app_store_assets/catalog.py` (`validate_apple_localizations`), `app_store_assets/records.py` (credential input rejection).
