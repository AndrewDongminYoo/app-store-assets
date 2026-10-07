# Shared runtime implementation evidence

Status: local review candidate. Approved local design/sequence: 2026-10-07 15:39 UTC. Originals were not modified. One implementer; no agent cluster or independent reviewer.

## Implemented slice

- Legacy prepare authorization bypass blocked; pure local preparation remains available.
- URL/full Git commit/complete runtime pin, isolated bootstrap before import, strict target/version paths and full input binding.
- Immutable input/runtime staging before remote lookup, exact Apple version IDs, Google account/app/track/status/notes, remote revision checks, account/app locks, partial/pending receipts and exact readback.
- New content-addressed metadata/asset/build history and explicit diffs preserve editing trees and earlier records. Cache tampering/additions and concurrent publication are tested.
- Frozen Apple/Google catalog, decoded format/extension/alpha/dimension/count/text validation, locked ImageMagick/oxipng normalization, deterministic PNG/JPEG output and an app-owned staged composer protocol. Provenance remains widget/import.
- Effect-separated CLI and argv JSON adapters, sanitized environments, build-only command construction, explicit native inspection/source/guard evidence for live artifacts.
- Ruby Fastlane 2.240.1 adapters: exact Apple listing versions, scoped image deletion/upload/order; Google abort-only read sessions, write-edit recheck, explicit draft/track release effects and uploaded image IDs for transformed readback.
- Mirae pinned launcher/profile, app-owned artwork adapter, fixture builder, default-blocked account/signing paths and legacy lane delegation. Other consumers are not migrated.

## Verification

The shared suite runs 107 tests: **102 passed, five legacy personal Fastfile integrations skipped**. Real pinned Fastlane screenshot reader checks and actual Supply image model are enabled. Ruby syntax and Git diff whitespace checks pass. Test providers replace external boundaries; no live authentication/network/store transfer was performed.

Meaningful RED/GREEN evidence includes the legacy bypass, plan/runtime/native identity mutations, AAB replacement during lookup, omitted image classes, pending/partial retry and concurrency, cache corruption, command environment/argv, actual SDK image fields, write-edit drift, transformed image readback, dry-run verify, receipt collisions, added staged executables, false native guards, ignored bytecode caches, incomplete live build evidence, composer/JPEG output explicit existing-image deletion policy and version-named changelog mismatch and mutation between dependency verification/import and asset-manifest cache/provenance tampering.

The Mirae six host tests exercise native mappings, no-home doctor, legacy bypass blocking, build-only argv, and both Apple/Google fixture workflows through generate/build-record -> download/diff -> plan/dry-run -> two preflights -> immutable upload -> readback. Final clean-clone logs and original-state evidence are stored in the execution workspace rather than copied into this package. Clean-clone object transport is local; the declared remote URL/commit identity is checked. The local candidate commits are not remotely published yet.

## Remaining gates and limitations

- No actual authentication/transfer, external processing/readback, account permission/group discovery, signed build, physical-device capture or app release validation.
- Mirae signed live builds remain blocked until a reviewed protected signing/native artifact inspection adapter exists. Fixture artifacts cannot qualify as live builds.
- Native Firebase/Steam/Toss/browser/OTA adapters, unsupported/new image classes, new Apple locale/version creation and localized binary beta notes remain blocked.
- Pending/partial attempts can be verified. If exact readback cannot reconcile partial effects, recovery needs a separately reviewed workflow; there is no implicit rollback or force-retry.
- Local target locks do not coordinate other machines; remote rechecks/readback remain necessary. Provider sessions/readbacks do not prove an atomic cross-machine transaction.
- JSON schemas document record shapes; Python validators enforce richer path/target/runtime/record contracts. Required submission classes/readiness are separate from accepted images.
- LICENSE and visibility remain owner decisions. No public publication, push, PR, merge or original-repository integration was performed.
- A single-author self-review has less independence than a fresh reviewer. A separately authorized integration should receive independent review.

## Reproduce

```bash
APP_STORE_ASSETS_FASTLANE_SOURCE=/absolute/path/to/fastlane-2.240.1 \
APP_STORE_ASSETS_READER_RUBY=/absolute/path/to/ruby \
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
ruby -c lib/fastlane_assets.rb
ruby -c lib/store_provider.rb
git diff --check
```

Original integration/source states and isolated candidate commit IDs belong to the workspace handoff. Do not apply a candidate wholesale over concurrent original work.
