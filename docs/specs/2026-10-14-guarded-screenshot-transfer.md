# Guarded Screenshot Transfer

## Status and scope

This specification answers [issue #28](https://github.com/AndrewDongminYoo/app-store-assets/issues/28), "Build the guarded screenshot transfer adapter".
The operator approved the plan on 2026-10-14 and, after the first draft (pull request #30) did not converge in review, chose to narrow it to the invariants below.
It adds no code; [the implementation plan](../plans/2026-10-14-guarded-screenshot-transfer.md) splits the code into separate pull requests and owns step order, provider details and their tests.

The adapter transfers App Store screenshots for one Apple iOS target from a reviewed offline plan.
`make_plan` already rejects macOS image operations.
Google Play images, App Previews, metadata text, binaries and review submission are out of scope.
The adapter adds no service, database or capture abstraction, and it does not change how images are captured, composed or prepared.

## Terms

- **Plan**: the record that `make_plan` in `app_store_assets/planning.py` returns for operation `images`, as `{"payload": ..., "digest": ...}`.
- **Target**: the plan's `target` identity, as `target_identity` in `app_store_assets/contracts.py` validates it; for Apple, `app_id` is the bundle identifier.
- **Declared group**: the ordered screenshots of one locale and one display class (slot) whose pair is a key pair of the plan's `listing.images`.
  `make_plan` compares `replacement.locales` and `replacement.slots` with the listing only as separate sets, so a declared locale and a declared slot that the listing does not pair form no declared group.
- **Preserved set**: every other screenshot set of a declared locale.
- **Supplied snapshot**: the plan's `remote` field, the `metadata-snapshot` that the target supplies.
- **Remote write**: any App Store Connect call that creates, uploads, deletes or reorders a screenshot or a screenshot set.

## Architecture

The transport is Ruby Spaceship from fastlane 2.240.1, in a new entrypoint of `lib/fastlane_assets.rb`.
Python's standard library has no ES256 signing, so the App Store Connect token cannot be made in the Python package without a new dependency.
The read-only `app_store_assets` package re-derives the plan; `app_store_assets_local.transfer` validates the approval record, stages checked bytes and returns the verified intent without a network call.
The legacy `AppStoreAssets.prepare` stays blocked, and loading `lib/fastlane_assets.rb` keeps working without the fastlane gem.

## Approval record

The offline plan type does not change: `type: offline-release-plan`, `executable: false` and `effects: []`, which `verify_plan` keeps enforcing.
Execution authority comes from a separate record that the operator writes for one plan:

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

The record follows the existing exact-key rules, its `target` passes `target_identity` and equals the plan's whole `target` (including `account_id` when the plan has one), `operation` is `images`, and it holds no credential, key path or token.
It is not a plan input, because the plan digest would then depend on its own approval, and it is read with the same `safe_path` checks as other inputs.

## Invariants

Each invariant holds for every run, whatever the step order or provider behavior; [the plan](../plans/2026-10-14-guarded-screenshot-transfer.md) names how each is met and tested.

1. **Bound authority.** A run starts only with a plan that `verify_plan` re-derives unchanged from the current inputs and an approval record that matches that plan's digest, whole target and operation.
2. **Checked bytes.** Every planned image of every declared group is read once and matches its plan SHA-256 before any action is chosen.
   Every value compared with App Store Connect (the MD5 that `source_file_checksum` reports) and every uploaded byte comes from those checked bytes, never from a second read of the source path.
3. **Fresh remote.** Before any remote write, a live read through Spaceship must equal the supplied snapshot for every declared group, the version must be the snapshot's `version_id` with the approved build attached, and the version must be editable with no active review.
   A snapshot field with no defined live equivalent fails the comparison; it is never skipped.
4. **Declared scope.** Remote writes touch declared groups only.
   A group is replaced (deleted and uploaded again) only when `replacement.allow_delete` is `true`; otherwise a non-empty group that differs from the plan refuses the run.
   Preserved sets and undeclared locales are never written.
5. **Decide before writing.** Every check of invariants 1 to 4, every group's action, and the health of every group left unchanged are settled before the first remote write.
   Any refusal means no remote write at all.
6. **Bounded waits.** Every wait has a finite, configured upper bound: the adapter's own polling and every provider call, including the provider's internal retries and request timeouts.
   Reaching a bound is a failure.
7. **Readback or fail.** A run succeeds only when a final live read shows, for every declared group, the planned count, the planned MD5 values in order, and every screenshot processed; the approved build still attached and the version still editable with no active review; and every preserved set unchanged.
   Anything else exits non-zero and names the groups that changed before the failure.
   This read sees only changes that remain visible, so a concurrent edit that the transfer overwrote cannot be detected; the [writer window](#operator-preconditions) prevents it instead.
8. **One result.** Standard output carries exactly one JSON result (plan digest, target, and per declared group its action, readback result and remote screenshot IDs); provider output goes to standard error.
   The run writes no file into the repository and no record of its own.
9. **No promotion, no secrets.** Asset provenance stays `unverified-import`, and no key material, key path or token appears in the repository, a plan, an approval record or a result.

An approval record therefore authorizes a run only while the live remote state still equals the supplied snapshot: once a run has written, invariant 3 refuses the same record again, and a run that wrote nothing can be repeated.
A retry after a partial failure needs a new snapshot, a new plan and a new approval record.

## Operator preconditions

The adapter cannot verify these; like the authorization that `AGENTS.md` requires, the operator declares them before a run.

- **Authorization**: explicit operator authorization for the target app and for each operation of the run (upload, and deletion when `allow_delete` is `true`).
- **Writer window**: App Store Connect has no conditional write, so from the live read to the final read no other tool, machine, fastlane or deliver run, or App Store Connect web edit may write the target's screenshots, select a different build, or change the version's state, including a review submission.
- **Credentials**: Spaceship's existing login, an App Store Connect API key or an Apple ID session, configured outside this repository; the personal lanes use an Apple ID (`FASTLANE_APPLE_ID`) today.

Two runs for the same target on one machine must not overlap; the plan defines the local lock that refuses the second run.

## Verification

All automated verification uses a fake App Store Connect in place of the Spaceship objects, and the default test command needs no fastlane gem, network access or credentials.
Each invariant has at least one test that fails when its guard is removed, and the plan lists the fake states for each unit.
A real upload or placement deletion happens only in the plan's final authorized smoke run.
Review submission remains out of scope, including that smoke run.

## Sources

- Current contracts: `app_store_assets/planning.py` (`make_plan`, `verify_plan`), `app_store_assets/contracts.py` (`exact_keys`, `target_identity`), `app_store_assets/metadata.py` (`remote_observation`, `validate_public_metadata`), `app_store_assets/catalog.py` (`validate_apple_localizations`), `app_store_assets/records.py` (`safe_path`, credential input rejection).
- The fastlane 2.240.1 provider behaviors that the invariants account for, with their source links, are listed in [the plan](../plans/2026-10-14-guarded-screenshot-transfer.md#provider-behaviors).
- QuestKeeper store-asset precedent, as [the first-stage contract](screenshot-bundles.md#sources) cites it: deliver's deduplication keyed on a checksum that was not ready produced 10 − N duplicates and a vacuous "Successfully uploaded" line, which is why invariant 7 trusts only a readback.
- The first draft and its six review rounds: pull request #30 and `docs/notes/2026-10-14-pr-loop-guarded-screenshot-transfer-spec.md`.
