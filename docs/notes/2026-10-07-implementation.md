# Shared runtime implementation evidence

Status: local review candidate. Approved local design/sequence: 2026-10-07 15:39 UTC. Originals were not modified. One implementer plus one user-authorized independent final reviewer; no agent cluster.

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

The shared suite runs 113 tests: **108 passed, five legacy personal Fastfile integrations skipped**. Real pinned Fastlane screenshot reader checks, the actual Supply image model and the actual Supply bundle return method with a fake transport are enabled. Ruby syntax and Git diff whitespace checks pass. Test providers replace external boundaries; no live authentication/network/store transfer was performed.

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
- One independent final review found five reproducible defects; all five were corrected and covered by regressions. This is local host evidence, not live provider acceptance.

## Final independent review fixes

The reviewer inspected initial shared commit `32ad52b` and Mirae commit `1062076d` using synthetic SDK boundaries and installed Fastlane 2.240.1 source. Four P1 defects and one P2 defect were reproduced before correction:

- Google binary upload called `.version_code` on Supply's integer return. It now checks the scalar; the real `Supply::Client#upload_bundle` runs against a fake transport in a regression.
- Downloaded images added local `file`/`sha256` annotations absent from fresh provider snapshots. Plans now compare only provider-observed image fields while validating and staging the complete immutable downloaded inventory. Provider ID/revision/checksum/order/processing changes still block.
- Apple build selection ignored the actual pre-release platform. It now filters IOS/MAC_OS, reports the actual platform, and binary readback rejects missing/conflicting platforms.
- Alternate `--state` paths bypassed pending/concurrent guards. Actual execution now requires the canonical `build/store-assets` registry; other snapshot commands may still choose local output state.
- Google `description` was written as `full_description` but never verified. Plans canonicalize the alias before digest/validation/readback and reject conflicting aliases; the native writer accepts canonical keys only.

Regressions live in `tests/test_provider.py`, `tests/test_execution.py` and `tests/test_planning.py`. The fixed SDK interface is exercised without authentication/network, and both Apple/Google nonempty download paths are covered. Source/runtime mutation, immutable downloaded bytes and original P1 regressions remain part of the full suite.

## Exact skipped checks

The five tests in `FastlaneIntegrationTests` are skipped because `APP_STORE_ASSETS_PERSONAL_ROOT` is unset:

- `test_legacy_metadata_lanes_are_blocked_before_replacement`
- `test_invalid_images_stop_before_upload_or_account_lookup`
- `test_legacy_alpha_inputs_do_not_authorize_replacement`
- `test_reader_incompatible_inputs_stop_before_external_calls`
- `test_metadata_only_option_does_not_require_a_screenshot_tool`

Their harness copies actual Mirae/Ttush/Kkom Fastfiles into temporary repositories. Current authorization permits reuse only from Mirae/app-store-assets, so the cross-consumer suite is not run or replaced with counterfeit personal checkouts. These are skipped legacy integration checks, not missing credential tests. Synthetic legacy-bridge tests and the migrated Mirae pilot run separately; unmodified original consumers remain unverified under this package.

## Formatter evidence

Trunk CLI 1.25.0 could not initialize: a writable `/tmp` cache retry failed DNS for `trunk.io`; a direct DNS lookup confirmed the failure. Existing cache tools were invoked directly, without installation or network: Prettier 3.9.9, markdownlint 0.49.1, isort 9.0.2, Ruff 0.16.10, shfmt 3.14.1 and ShellCheck 0.11.0. The pinned Black 26.5.1 cache directory is empty; installed Black 26.10.0 provides an explicitly different-version formatting check. Mirae's changed Markdown/JSON/YAML, launcher and four new Python files are checked directly with the repository lint configurations. This does not claim the unavailable exact Trunk/Black gate passed.

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
