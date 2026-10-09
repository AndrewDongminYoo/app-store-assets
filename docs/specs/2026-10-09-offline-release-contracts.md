# Offline release contracts (unit B)

Base: merged A at `542840600d8f6ee006d1e9936f7f4fe816cbc6e2`.
Source reference: preserved PR3 at `9fc53959e52402f7dbfe6d3fae93560abdd4aa09`.

## Boundary

The separate `python3 -B -m app_store_assets` entry point offers only doctor,
plan, diff, import and export. Existing `assets.py` and the fail-closed Ruby
bridge remain unchanged. There are no provider, command adapter, credential,
download, generation, native-build, execution, receipt or attempt modules.
The `-B` flag is required (or set `PYTHONDONTWRITEBYTECODE=1`): runtime
verification rejects bytecode caches. A default Python invocation fails closed;
remove only task-created caches before retrying with bytecode disabled.
Image validation may invoke the existing local ImageMagick decoder with an
isolated home. Git identity queries disable personal configuration and hooks.
No authenticated account, current remote state or native validity is asserted.

Profiles are explicitly `type: offline-profile`, schema version 1. Strict
validators reject effect configuration (`provider`, `builds`, `recipes`) rather
than importing it. Apple iOS/macOS and Google Android identities include an
explicit account label, app, flavor, stage and numeric version/build; Google
also requires track and release status. A declared account ID, if present,
is public identity data, not proof of authentication. Exact runtime origin,
commit and complete executable/catalog/schema inventory must match a clean
checkout, including untracked files. Source inputs and JSON records are bounded,
canonical, symlink-free public paths; private filenames are rejected before reads.

Plans have `type: offline-release-plan`, `executable: false`, `effects: []`,
`remote_verified: false` and a canonical payload digest. They bind runtime,
profile, public source inventory, catalog, target and relevant local records.
`planned_changes` describes proposed store changes without authorizing them.
Revalidation rebuilds the plan and rejects changed input/target/runtime bytes.
Doctor verifies only the local profile/runtime/source inventory.

## Required validation

- Apple metadata/image plans require a supplied exact-target snapshot with a
  nonempty version ID, `editable is true` and `review_active is false`, plus
  available version/AppInfo localizations. These claims may be stale or supplied
  incorrectly: output must explicitly label them as supplied, freshness unverified.
- Nonempty URL fields require an absolute HTTP(S) URL with host, valid port and
  no whitespace, user information or credential query keys. Empty optional URLs
  remain explicit clears; proposed empty Apple support/privacy URLs are rejected.
  Empty fields in a supplied draft snapshot are existing observations, not proposed clears.
  Supplied Apple names contain 2–30 characters. Catalog rules are frozen local
  rules, not a live store acceptance oracle.
- Image plans retain each decoded/validated image's computed SHA256 and size in
  the listing, including when input omitted SHA256. Immutable asset snapshots
  match the exact target, ordered listing inventory and hashes. Replacement
  locales/slots/deletion policy are explicit and cover exactly the listed groups.
  Imported capture provenance always remains `unverified-import`.
- Binary descriptors and build records both declare `kind`. Google APK and AAB
  are both supported as offline containers: ZIP central-directory structure
  distinguishes APK (`AndroidManifest.xml`) from AAB
  (`BundleConfig.pb` and `base/manifest/AndroidManifest.xml`). Apple iOS IPA uses
  one `Payload/*.app/Info.plist`. Declared kind, extension, platform, container,
  target and SHA256 must agree. This is not native inspection/signing evidence;
  D owns that verification, E owns approved endpoint capability. No AAB-only
  transport policy is selected here. Other binary formats fail closed.
- Supplied live build records require the existing source commit/input and
  positive native-guard/inspector declarations, clearly labeled as unverified
  supplied inspection claims. No inspector executable is read or run.
- Immutable snapshots use content-addressed manifests and exact public file
  inventories; a concurrent publisher may reuse only a byte-validated winner.
  The shared local staging primitive verifies captured copies and imports no
  executor. Local import/export reserve new outputs and preserve editing trees.
- Dry-run validates the selected operation and inputs but performs no local
  output write. Unsupported operations/options fail before profile/provider
  access. Doctor/plan/diff never create output/history/attempt directories.

## Acceptance and limits

Regression owners: 4226322791, 4226322794, 4226322797, 4227029536 and the
offline artifact-kind part of 4226322800. E's transport part remains open.
C's render race 4227029532 and all other C/D/E effects remain out of scope.
Preserve all A gates and report the existing six Ttush fixture failures without
skips or weakened assertions. Tests use synthetic temporary repositories and
copied public Fastfiles with network/native/store effects blocked.

Local implementation, tests, at most two independent review/repair cycles,
normal local commits and a PR draft are authorized. Remote push/PR/reviews,
PR3 mutation, merge, consumer/pin changes and C/D/E work require separate authority.
Original working trees, the original shared repository's note/stash, and all
nine PR3 / two A HEAD-round evidence remain preserved.

References checked 2026-10-09: [Apple app information](https://developer.apple.com/help/app-store-connect/reference/app-information/app-information/),
[Apple platform version information](https://developer.apple.com/help/app-store-connect/reference/app-information/platform-version-information/).
