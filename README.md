# App Store Assets

Shared image-bundle preparation for personal App Store projects.
Existing project capture and artwork generators remain the source of images.
The first adoption covers Mirae, Ttush Push, and Kkomkkomi Fastlane uploads, plus the App Store copyright fix in Chef al Mando's composer.

## Requirements

Python 3.9 or newer, ImageMagick 7 (`magick`), and Ruby for the Fastlane bridge.
No new Python package or Ruby gem is required.
Keep this checkout beside the personal app repositories or set `APP_STORE_ASSETS_ROOT` to its absolute path.
The [shared repository](https://github.com/AndrewDongminYoo/app-store-assets) is public.
Use a reviewed runtime commit for reproducible installation.
Missing tooling stops screenshot uploads with an explicit error.

## Runtime Checkout

The stage-1 runtime pin `e0d3691b455ec2c27606fbda5b22f09f5a9d3483`, also included in `d9682e6`, has reader-compatibility and cache-publication defects.
Do not use those revisions for store uploads.
The historical replacement candidate `7597d47f3ce36cac3462155b0c8a489a441e62a8` still has the legacy transfer-enabling `prepare` behavior.
Do not deploy that revision, or the older pins above, as a runtime providing the legacy transfer block described below.
This extraction approves no replacement deployment pin and supplies no deployment checkout command.
Before installing the updated bridge, separately review and approve a merged runtime revision containing the block and explicit `prepare_local` entrypoint.

Project lane adoption remains in each owning app repository; those app changes are not included in this repository's publication.

## Prepare without uploading

```bash
python3 assets.py prepare-screenshots \
  --source ../mirae/fastlane/metadata/ios \
  --subdir images/iphone65 \
  --out ../mirae/build/store-assets/ios-bundles \
  --project mirae --bundle-id kr.mirae.app
```

The command returns JSON containing `bundle` and `screenshots_path`.
Each locale is flattened to the direct image layout Fastlane reads.
The bundle directory is named from the manifest hash and contains final hashes, original hashes, sizes, profiles, and the explicit `replace-localized-sets` policy.
`validate` re-decodes images and compares final hashes and inventory.
Preparation additionally compares a reused bundle's manifest with the manifest freshly computed from the source.
Concurrent preparations validate and reuse the atomically published winner.

```bash
python3 assets.py validate /absolute/path/to/bundle
python3 -m unittest discover -s tests -v
ruby -c lib/fastlane_assets.rb
```

The default suite runs the standalone CLI tests and explicitly skips consumer integration tests.
GitHub Actions runs the unoptioned default test command and Ruby syntax checks on pull requests targeting `main` or the stacked `split/offline-read-boundaries` branch, and pushes to `main`.
The single Ubuntu 24.04 job installs ImageMagick 7 through the runner's existing Homebrew and uses Python 3.12 with read-only repository permissions.
Consumer integration and the optional Fastlane reader checks remain local because they require additional checkouts or reader dependencies.
To verify actual adopted Fastfiles, set `APP_STORE_ASSETS_PERSONAL_ROOT` to the folder containing the personal `mirae`, `ttush_push`, and `kkomkkomi` checkouts with the stage-1 lane changes.

```bash
APP_STORE_ASSETS_PERSONAL_ROOT=/absolute/personal/root python3 -m unittest discover -s tests -v
```

To compare the manifest with the actual Fastlane 2.240.1 loader, point to its unpacked source and a Ruby interpreter with its existing reader dependencies.
This check reads temporary files and makes no store calls.

```bash
APP_STORE_ASSETS_FASTLANE_SOURCE=/absolute/path/to/fastlane-2.240.1 \
APP_STORE_ASSETS_READER_RUBY=/absolute/path/to/ruby \
python3 -m unittest discover -s tests -v
```

`--normalize-alpha` removes an unused alpha channel from an entirely opaque PNG in the prepared copy.
It rejects actual transparent pixels, which require an explicit background in the owning composer.
Original inputs remain unchanged.
PNG encoding excludes date and time chunks while retaining color metadata, so identical input bytes produce identical output within the same ImageMagick runtime.
Explicit local preparation can enable this option for opaque alpha inputs.

## Upload behavior

The legacy Ruby `AppStoreAssets.prepare` entrypoint is blocked before it starts a local process or returns options that a lane can use for screenshot transfer.
Consumers can explicitly call `AppStoreAssets.prepare_local` to prepare validated local bundles.
It returns `screenshots_path` without `overwrite_screenshots`; that path is local output and does not authorize an upload.
The guarded transfer entrypoint below is separate from this legacy boundary.

Local preparation rejects hidden screenshots, mixed-case extensions such as `.Png`, and mismatched file formats.
Screenshot transfer requires a separately reviewed plan, exact target and complete local/remote placement policy.
The existing external Fastlane replacement behavior can affect remote display classes absent from a local tree.
Consumers that call Fastlane directly need their own guarded integration; this bridge cannot block those calls.
The Mirae, Ttush, and Kkom negative and metadata-only opt-in cases passed with external actions stubbed at the consumer revisions recorded in [the 2026-10-14 integration evidence](docs/notes/2026-10-14-mirae-direct-lanes-integration.md).
The fixture copies Mirae's required local helper and checks its current plan/digest requirement, including metadata-only calls; the [fixture contract](docs/specs/2026-10-16-fastlane-integration-fixture.md) records the correction for issue #41.

The Python commands remain offline; the Ruby transfer entrypoint uses an already-authenticated Spaceship session and can upload approved screenshots.
No entrypoint logs in or submits review.
Fastlane lane execution remains an external action requiring authorization.
The [guarded screenshot transfer specification](docs/specs/2026-10-14-guarded-screenshot-transfer.md) defines the readback and transfer contract.

## Evidence limits

The initial manifest labels existing inputs `unverified-import`.
It records file provenance, not the build that originally rendered the image.
It does not assert required-slot completeness, text readability, visual quality, safe-area compliance, or App Store acceptance.
The current dimension allowlist covers the adopted iPhone and iPad pipelines; it is not a complete Apple device catalog.
Duo and Creative Assets require the next reference-data and provenance contract rather than aliases for existing phone screenshots.

See [the rollout](docs/plans/2026-10-07-rollout.md) and [the first-stage contract](docs/specs/screenshot-bundles.md).

## Offline read commands

`python3 -B -m app_store_assets COMMAND --root PROJECT --target NAME`, where
`COMMAND` is one of `doctor`, `plan` or `diff`,
uses an explicitly pinned local runtime and supplied public records. `plan` is
an intent record with `executable: false`; no command constructs a provider or
writes project state. `diff` additionally takes `--before` and `--after`.
`--dry-run` keeps the same read-only behavior. Image validation may create
private temporary decoder files which are removed on completion.

When a target declares `assets.manifest`, `doctor` validates the local listing and asset snapshot without reading `remote`.
It binds the ordered locale/slot paths and image hashes, checks the snapshot's files against their bytes, and compares recorded import inputs and source export with the listing's provenance.
Its input inventory includes the checked listing, snapshots and images; `plan --operation images` remains the selected-version and replacement-policy check.

The profile lists a public runtime URL, exact Git commit, complete runtime hash
inventory and each app/platform/account/flavor/stage/version/track identity.
Unknown keys and malformed nested values fail closed in every target, including
unselected targets. Public metadata URL queries accept only `lang`, `hl` or
`locale` with a locale value; credential queries and fragments are rejected.
All file reads reject symlinks in any component. Private name patterns are
rejected in every component of a raw path, and in every component below the
trusted root of a `safe_path` result; that root's trusted absolute ancestors are
not re-checked. Reads capture bounded bytes and bind parsed bytes to final hashes.
Snapshots validate the complete supported record as well as their address and
exact file inventory. Python validators are authoritative; the JSON schema files
are structural summaries and do not replace runtime validation.

The `app_store_assets` reader package contains no import/export/staging/publisher implementation or writer import.
Those functions live in `app_store_assets_local`; read plans retain no execution authority.
Native identity, signing, provider account and remote freshness remain unverified.

Catalog rules are frozen to `catalog.CATALOG_SHA256`: each read validates the
captured digest and the complete structure before use. Changing frozen rules
requires updating their version and this explicit digest together. Image width,
height and size annotations must agree with decoded captured bytes, including
immutable asset snapshots.

The separate local extension publishes only metadata and asset records. It
rejects build publication; binary read plans still bind explicitly supplied
APK/AAB/IPA files through B1. Import rejects listing files that overlap reserved
history directories or predicted snapshot addresses, including in dry-run mode.
Local copy operations charge supplied bytes before reading paths and bound each
capture by the remaining 1 GiB total budget (64 MiB per image, 8 MiB per text).
Snapshot manifests, export manifests and final listings must serialize within
the public reader's 8 MiB limit before any durable output is created.

## Read-only snapshot export

`AppStoreAssets.export_snapshot(target:, output:)` in `lib/fastlane_assets.rb` writes the `metadata-snapshot` record that a plan target supplies as its remote state.
Call it from a consumer Fastlane lane after the lane has authenticated Spaceship; this repository has no such lane, and loading the library still needs no fastlane gem.
It supports one Apple iOS target, makes read calls only, and ends each provider call at `deadline:` seconds (`SNAPSHOT_DEFAULT_DEADLINE`, at most `SNAPSHOT_MAX_DEADLINE`).
It refuses an existing output path, an output directory inside this checkout, and a record that the Python validators reject; it never replaces a file.
It also refuses, and writes nothing, for a missing app, a missing or ambiguous version, an attached build other than the target's, a duplicate locale or screenshot set, or a full provider page.
A version that is not editable or has an active review is recorded with `editable` or `review_active` set, and the planner refuses it later; a version with no attached build has no `binary` key.
`app_info_id` and the app-info fields come only from an editable app info, never from one that is waiting for review; without one, `app_info_id` is `null`.
A screenshot set that exists with no screenshots is an empty list, and a set that does not exist has no key.
Standard output carries one JSON result with the output path, the record's SHA-256 and counts; provider output goes to standard error.
The record is an observation at one point in time; [the guarded screenshot transfer specification](docs/specs/2026-10-14-guarded-screenshot-transfer.md) defines how a later run compares it with the live state.

## Verify transfer approval and stage bytes

The U2 command in `app_store_assets_local.transfer` re-derives an Apple iOS images plan, checks an operator-written [transfer approval](docs/specs/2026-10-14-guarded-screenshot-transfer.md#approval-record), and stages every planned image from SHA-256-checked bytes.
The approval must name the plan digest and its whole target, including `account_id` when present.
The plan keeps `executable: false` and `effects: []`.
This command makes no network call and grants no implicit authorization to upload or delete placements.

```bash
stage_dir="$(python3 -c 'import pathlib, tempfile; print(pathlib.Path(tempfile.mkdtemp(prefix="store-transfer-")).resolve())')"
python3 -B -m app_store_assets_local.transfer \
  --root /absolute/path/to/personal/app \
  --plan reviewed-plan.json \
  --approval transfer-approval.json \
  --staging-dir "$stage_dir"
```

Plan and approval paths are public paths relative to `--root`; the approval is not a plan input.
The staging directory must already exist, be empty, be private to the current user, and have an absolute path outside the app and runtime checkouts, with no symlink or parent traversal.
The caller owns the directory and removes it after use.
On failure the command removes only files it created; it never replaces existing files.

Standard output contains one `verified-transfer-intent` JSON document with the plan digest, target, mode, supplied remote observation, replacement policy, unchanged provenance, and the listing's actual locale/slot pairs.
Each image has a private `staged_path`, SHA-256 and MD5 derived from the same captured bytes.
MD5 is only a provider comparison value; SHA-256 binds the approved bytes.
Real uploads require the specification's explicit operator authorization and writer window.

## Verify the live screenshot state

`AppStoreAssets.transfer_screenshots` defaults to `mode: "read-only"`.
Call it from an authenticated Fastlane lane with the same whole target used by the reviewed plan and approval:

```ruby
AppStoreAssets.transfer_screenshots(
  root: "/absolute/path/to/personal/app",
  target: approved_target,
  plan: "reviewed-plan.json",
  approval: "transfer-approval.json",
  mode: "read-only",
  deadline: 120,
  verification_deadline: 120
)
```

Plan and approval paths remain relative to `root`.
The entrypoint takes a bundle-ID lock before calling U2, owns its private staging directory, compares the supplied observation with live Spaceship reads, and removes its staging directory and its own lock on exit.
The lock is `/tmp/app-store-assets-transfer-<SHA-256 of bundle ID>.lock`, independent of `TMPDIR` and the app checkout.
An existing lock refuses the run; only the operator may remove a stale lock after checking that no run owns it.
Cleanup isolates each owned entry in a private sibling directory and rechecks its inode before deletion.
A detected replacement refuses the run and is retained at the path reported on standard error for operator recovery.

Every provider call has the configured `deadline`, and each local Python verification has `verification_deadline`; both must be positive and at most 600 seconds.
Python input and output are bounded to 8 MiB per stream, and a timed-out verifier process group is killed.
Provider output goes to standard error, including an already-created STDOUT logger.
Standard output contains one JSON result with the plan digest, target, actual declared groups, snapshot comparison results, remote screenshot IDs, and preserved sets of the declared locales.

The read-only mode verifies snapshot freshness and the approved attached build.
It does not choose upload or replacement actions or certify screenshot processing completion.
The mode rejects snapshot fields that have no live mapping, and keeps provenance as `unverified-import`.
The exact mappings and fake-provider acceptance cases are in the [U3 plan](docs/plans/2026-10-14-guarded-screenshot-transfer.md#u3-live-mappings-and-entrypoint).

## Transfer approved screenshots

After the operator authorizes the target and operations and establishes the [writer window](docs/specs/2026-10-14-guarded-screenshot-transfer.md#operator-preconditions), use the same entrypoint with `mode: "transfer"`.
The approval record, reviewed plan and fresh supplied snapshot are still required.
The legacy `prepare` entrypoint remains blocked.

The adapter checks every staged image, selects every declared group's action, and waits for every unchanged group to finish processing before its first remote write.
All declared localization and existing set IDs must be valid before that first write.
Missing remote checksums are polled before action selection; they cannot by themselves trigger replacement, and screenshot IDs must stay unchanged during this preflight poll.
With deletion authorized, a preflight-confirmed `AWAITING_UPLOAD` placeholder may be replaced without waiting for its missing checksum; a retry still needs a new snapshot, plan and approval, and the exclusive writer window.
It creates absent sets, uploads empty groups, and replaces different non-empty groups only when the reviewed plan has `replacement.allow_delete: true`.
Replacement deletes screenshots within the declared set; it does not delete preserved sets.
Uploads use staged paths with explicit positions and `wait_for_processing: false`.

Optional bounds are `group_deadline: 600`, `poll_interval: 5`, and `request_timeout: 60`, all in seconds, positive and at most 600.
Each group's writes and readback share its group deadline; each provider call also has the existing `deadline: 120` limit.
The adapter temporarily sets `SPACESHIP_TIMEOUT` to the request timeout rounded up to whole seconds and `SPACESHIP_SCREENSHOT_UPLOAD_TIMEOUT` to the group limit rounded up to whole minutes, at least one minute, and restores both variables on exit.
The adapter deadline still bounds provider retries when their internal timeout is longer.

The transfer result reports `upload`, `replace`, or `unchanged` for each declared pair, its readback completion and checksum match, and the remote screenshot IDs.
Success requires the planned count and MD5 order, completed processing, unchanged preserved sets, and the approved build and editable version without active review in the final read.
One corrective reorder is allowed when only the uploaded group's order differs.
A failure reports groups that may have changed, including calls whose response timed out; it does not roll back remote writes.
After a partial failure, obtain a new snapshot, plan and approval record before retrying.
Provenance remains `unverified-import`.

The separately authorized [kkomkkomi U5 smoke run](docs/notes/2026-10-16-kkomkkomi-u5-smoke.md) completed on 2026-10-16 for `1.1.1 (5)`.
It replaced four screenshots in each of `en-US/APP_IPHONE_67` and `ko/APP_IPHONE_67`; final live reads verified their ordered checksums and completed processing without a review submission.
