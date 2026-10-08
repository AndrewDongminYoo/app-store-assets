# App Store Assets Pipeline — Design for Review

Status: approved for local implementation at 2026-10-07 15:39 UTC. Host-only implementation evidence and remaining capability blockers are recorded in `../notes/2026-10-07-implementation.md`.

## Intent and boundaries

Make the existing `app-store-assets` repository the shared source for reproducible image generation, store specification validation, image/version history, metadata download/diff/tracking, explicit upload/download, and flavor/test-stage build/distribution orchestration. An agent should complete these operations without sending routine portal uploads back to the user.

Keep application capture, visual design, signing and native release rules in their application repositories. Reuse implementation only from Mirae and app-store-assets, excluding secrets, personal configuration and unnecessary branded logic. Cami is a structural reference only: copy no source, documentation, assets or fixtures. Earlier home-runtime code is review evidence, not an implicit implementation dependency or a source to copy without the stated reuse boundary.

This request authorizes design, local implementation and isolated tests. It does not authorize real store authentication/transfer, new credentials, account/permission changes, package publication, app release, visibility changes or pushes. The user will manage visibility. LICENSE remains undecided and does not block local implementation.

## Selected approach

Extend the existing Python-standard-library CLI and use Fastlane/Ruby as store adapters, ImageMagick/oxipng as image tools, and existing app commands as build/capture adapters. Preserve `assets.py prepare-screenshots` and `validate` compatibility. Add coherent `generate`, `build`, `download`, `diff`, `plan`, `execute`, and `verify` operations backed by one package.

A Fastlane-first orchestration layer is possible, but would move the existing Python manifest/validation contracts into Ruby and still need separate adapters for Godot, Toss and Steam. The Python coordinator with focused adapters reuses the current structure and is recommended. Add no service, database, universal capture framework, new tool repository or seven runtime forks.

The package belongs in `app-store-assets`. A consumer has its own profile/recipes, a thin launcher and a pinned Git dependency (initially a submodule). Pin the source URL, full commit and runtime inventory/hash manifest. Reject an unexpected commit, modified/missing/additional executable input or conflicting package override before running it. All CLI operations bind the whole executable package; image-library approval alone is insufficient. No runtime import, fallback, resolver or mandatory setup may depend on `~/.codex` or an undeclared sibling checkout. The home skill becomes usage documentation only.

## Components and ownership

| Component | Owns | Interface / dependencies |
| --- | --- | --- |
| CLI/profile resolver | Explicit project, target, recipe and operation selection | JSON configuration, schema version and capabilities; no auth in doctor/plan |
| Manifest/history | Immutable local asset/build/metadata records and ordered inventories | SHA-256, relative paths, canonical JSON; content-addressed snapshots |
| Generation | Reviewed recipe execution, input staging, output validation/atomic publication | ImageMagick; optional locked oxipng; app capture/composer adapters |
| Specification catalog | Versioned store/slot rules and provenance of those rules | Locale, type/extension, dimensions/aspect, alpha, count and text limits; explicit supported slots |
| Metadata/snapshot manager | Download into new snapshots, normalization, diff and explicit local export | Provider readers; no destructive overwrite or automatic Git commit |
| Build adapters | Flavor/preset-specific build, identity/provenance and native guards | Existing Flutter/Godot/native commands; pass reviewed artifact paths explicitly |
| Store adapters | Account/target preflight, scoped upload/download and readback | Pinned Fastlane/native clients; capability-specific effects |
| Planner/executor | Input/code binding, immutable execution inputs, locks, receipts and failures | Shared contracts; no implicit submission, promotion or public release |

Keep units small and colocate their tests. Proposed package location: `app_store_assets/`, with provider/build adapter submodules and JSON schemas under `schemas/`. The root CLI remains a thin compatibility facade. Final file/function-level planning follows design review.

## Versioned records

1. **Asset manifest:** schema/rules version, project/account/store/app/locale/slot, ordered source/final file inventories and hashes, recipe/helper/font/template hashes, actual toolchain fingerprint, generation inputs and capture evidence type. Preserve original captures and old bundles. A generated preview, widget-rendered image or imported image never becomes verified native capture by matching the current commit alone.
2. **Build record:** source commit plus declared input inventory, target/flavor/preset, version/build number, toolchain, artifact identity/hash, signing/native guard evidence and explicit derived-artifact steps. Reproducible inputs do not imply bit-identical signed IPA/archive exports; record and verify the actual final bytes instead of making that claim.
3. **Metadata snapshot:** local/remote origin, account/app/platform/version ID/track, observed revision/time, allowlisted localized fields and ordered image groups, original remote identifiers/checksums where supplied. Downloads go to a new content-addressed directory; local editing trees remain intact. Diff distinguishes additions, edits, removals, ordering and omitted remote groups.
4. **Release plan/receipt:** selected target and effects, dependency/runtime/toolchain identities, application helpers/config/notes inventory, artifact/asset/metadata hashes, relevant remote snapshot IDs, reviewed digest, staged paths and attempt status/readback. An execution success remains `accepted_pending_verification` until provider-specific readback confirms the exact target and effects. Never equate a child exit code with publication.

Snapshots/receipts are project-local and ignored by default. An explicit export can version-control public metadata and approved image/source manifests. Keep signing keys, review/demo passwords, personal contact/private fields and raw authentication out of the public package, samples, logs and automatic exports. Do not create a central repository containing consumer assets. Image storage initially uses ordinary files plus manifests; do not introduce LFS or another storage service before a demonstrated need.

## Reproducible generation

Extract generic subprocess/input-check/staging mechanics from Mirae's ImageMagick pipeline and preserve app-specific composition through an adapter. Recipe inputs include capture files, fonts, overlays, copy, source metadata, command arguments and helper dependencies. Hash all declared inputs; stage them so changes during generation cannot alter reviewed work.

Use an explicit toolchain lock recording OS/architecture, ImageMagick version/build/delegates, encoder/oxipng, fonts and recipe/runtime identities. Strip nondeterministic encoding data using an explicit reviewed policy. Require repeated generation within the same locked toolchain to produce identical final bytes and manifests. Do not promise byte identity across different OS/encoders. A distinct toolchain produces a distinct generation identity and requires re-planning. A container-digest generation backend can be added if cross-host byte identity is required.

The current Mirae host uses ImageMagick 7.1.2-32 Q16-HDRI aarch64 and oxipng 10.2.1; these are observations, not a universal toolchain choice. Its widget-rendered artwork is recorded as widget-rendered evidence, not native-device capture.

Mirae's historical March capture specification lists different dimensions from the current screenshot-directory instructions and generator. The pilot records the current input contract explicitly: iOS/ring inputs 1242×2688, Android feature inputs 1080×2400; composed outputs are iOS 1242×2688 and Android 810×1440, six per store/locale. These are application recipe values, not universal store specifications. Keep the historical specification/evidence intact, document the selected contract, and block an unexplained recipe/spec disagreement instead of silently rewriting old results. Preserve existing locale mapping and raw-capture ordering separately from composed artwork ordering.

The specification catalog retains source URL/date and its own version; do not refresh rules silently during an approved operation. Validate decoded bytes, extension/format, alpha and exact slot inventory. Match the actual pinned Fastlane reader. Apple display classes and Google image types stay explicit; unsupported/new slots fail closed instead of being inferred from an old dimension allowlist.

## Download, tracking and provider capabilities

Apple and Google are the first store adapters. Use existing Fastlane download functionality behind explicit account/target selection and normalize into snapshots. Downloads must distinguish live/editable versions, exact version IDs, track/release context and all image classes. Do not preserve Mirae's iPhone-only filtering or destructive Android metadata wipe as shared behavior.

No store edit/commit/upload may occur during a read operation. If an API internally needs an edit/session for a read, declare and constrain that behavior and never commit it; do not describe an unverified backend as zero-mutation. Read/normalize only approved public listing fields by default; private review/auth fields require a separate protected input/output policy.

Support-store capability tables state which slots support local validation, generation, download, upload and readback. Implement Apple/Google first, then existing Toss/Steam/Firebase/native routes through their own adapters. Do not invent download/image APIs where the provider has none. An unsupported API slot can use an explicitly authorized account-bound browser adapter with the same file/target/effect/readback contract, or remain visibly blocked until that adapter exists. OTA updates are separate from store binaries; do not treat them as a generic publish operation.

Remote image services may transform image bytes. Readback records provider inventory/order/processing state and source checksum where available; raw downloaded-byte equality alone is not a universal proof of the uploaded source.

## Actual consumer mappings and build boundary

| Pilot target | Existing identity / behavior | Proposed default |
| --- | --- | --- |
| Mirae production / Android | `kr.mirae.app`, production AAB, Play internal | Preserve explicit `draft`; bind versionCode/changelog and selected track |
| Mirae production / iOS | `kr.mirae.app`, production IPA | TestFlight/binary and listing are distinct operations; no review submission |
| Mirae staging / Android | `kr.mirae.app.stg`, staging APK, Firebase distribution | Separate distribution capability; no automatic Play fallback |
| Mirae staging / iOS | `kr.mirae.app.stg`, staging IPA | Separate target; remote availability unverified |
| Mirae development | `kr.mirae.app.dev`, capture/dev schemes | Capture/testing only; binary store upload blocked by default |
| Godot/native consumer contract | Explicit export preset, application ID, clean source/build record and native checks | Adapter calls existing build/signing code; preserve archive re-signing/provisioning effects explicitly |

These identities come from Mirae's actual native flavor settings. Branded inputs and real profile values remain in Mirae; public package samples use synthetic identifiers. Store account/permission/group existence is not verified by local IDs.

Mirae's `merry build aab/ipa` also uploads. The pilot adapter must invoke a build-only command; never call that alias from preparation/dry-run. Resolve build numbers before generation and bind them to the build record, rather than computing timestamps again during upload. Godot/native adapters consume staged reviewed artifact paths and preserve app-owned signature, permission, privacy, version and symbol guards.

## Execution safety and failure behavior

- `doctor`, `plan`, `diff`, and dry-run are offline: no credentials, store calls/writes, upload, release, device install or implicit legacy lane. Display concrete commands/effects without running them.
- Local `build/generate` and remote `download/execute/verify` have separate execution/effect boundaries. Build adapters do not inherit store-upload credentials. Device capture requires a declared device operation and is not host-only asset verification.
- A plan binds app/platform/flavor/stage/account/store/track/version/build, runtime and all declared transitive helpers/config/notes, inventory and bytes. Before each effect, revalidate it; mutations/additions/removals invalidate the old digest.
- A command provider requires one staged Python/Ruby source entrypoint.
  Module-only, inline and native provider loaders fail closed during offline planning.
  Capture the complete approved input/runtime inventory into an anonymous, hash-verified archive before the first authenticated invocation.
  The child receives a read-only descriptor; supported imports, require/load, file reads and Bundler Gemfile/lock evaluation use captured bytes, including after a parent-directory rename.
  Ignore local Bundler configuration.
  Installed interpreters, standard libraries and SDKs remain trusted infrastructure; reviewed providers must use the supported loaders rather than spawn staged code or load staged native extensions.
- Upload immutable staged copies, including native artifacts, metadata and notes. Original-path verification just before process launch cannot eliminate the remote-lookup race. Pass staged paths through adapters; approved re-signing/export steps have their own staged inputs and derived output records.
- Apple listing operations bind the exact existing version ID and verify editability/review/display-class scope. Never select the highest editable version, create a version implicitly, or allow partial local sets to delete omitted remote classes. Screenshot replacement requires an explicit reviewed locale/class policy.
- Play release status, track and changelogs are explicit, and environment defaults cannot override the plan. Bundle upload, text/image upload and track promotion are separate effects.
- An offline plan can describe an unverified remote target. It is not executable as a verified transfer until a target snapshot/preflight resolves the exact intended target; any conflicting server state blocks and requires a new plan. Re-read after preflight and before transfer.
- Serialize execution by canonical account/app/store/target in the project workspace; retain an attempt record across failures. Reconcile remote pending state before a retry. Local locks alone do not prevent another machine from writing; remote revision checks/readback remain necessary.
- Never automatically roll back a partial remote write. Preserve failed/partial/pending receipts and prior snapshots. Recovery is a new explicit plan against observed remote state.
- The official legacy Ruby bridge must stop or delegate replacement to the guarded path. A prepare-only result must not silently enable `overwrite_screenshots:true` in an unguarded Fastfile.

## Acceptance and review points

The first pilot is a clean-clone Mirae production Apple/Google path with fake credentials, synthetic/approved local assets and store boundaries stubbed. It must run without `.codex`, sibling repositories, unpublished consumer state or real store authentication. Keep all seven original consumers and their unrelated changes untouched until the pilot has passed.

Regression acceptance covers the four original P1 failures, whole-runtime mutation and Kkom's legacy approval bypass, plus dry-run/read-only download boundaries, metadata conflicts, mismatched flavor/version/artifact, exact inventory, same-toolchain generation, paths with spaces/metacharacters, cache corruption and concurrent attempts. Tests use meaningful behavior checks and actual pinned Fastlane reader/transport with fake external boundaries where needed. Use no Cami or Kkom source fixtures in the new package; their review findings become synthetic contract cases.

For user review: approve the centralized package/adapter boundary and Mirae-first sequence. Proposed reproducibility scope is byte identity within one locked toolchain; cross-OS byte identity is the one optional requirement that changes implementation scope. LICENSE remains a later user choice before public package distribution. Actual authentication, external transfers, publication, PR/push and app releases remain separately authorized.

## References

- Existing review and reproductions: `review/REVIEW.md`, `review/reproduce.py`, `review/check_runtime_binding.py`, `review/check_kkom_bridge.py`; reuse contracts/assertions rather than copying prohibited application fixtures.
- Existing app-store-assets: `assets.py`, `lib/fastlane_assets.rb`, `docs/specs/screenshot-bundles.md`, tests and CI.
- Mirae: `scripts/screenshots/generate_store_artwork.py`, `sync_metadata.sh`, download scripts, `merry.yaml`, flavor settings and locked Fastlane 2.240.1.
- Mirae contracts: current `scripts/screenshots/AGENTS.md`; historical `docs/specs/2026-03-02-autoroute-screenshot-workflow.md`; `docs/specs/2026-09-14-release-plan-truthfulness.md`. The host-only pilot cannot close physical-device acceptance gaps.
- [Fastlane deliver](https://docs.fastlane.tools/actions/deliver/) and [supply](https://docs.fastlane.tools/actions/supply/) document listing download/upload facilities; exact selected-version behavior is also constrained by the prior local-source tests.
- [Apple screenshot specification](https://developer.apple.com/help/app-store-connect/reference/app-information/screenshot-specifications/). [Google listing assets](https://support.google.com/googleplay/android-developer/answer/9866151?hl=en) were subsequently verified for the frozen catalog on 2026-10-07. Unsupported device/API slots remain explicit blockers.
