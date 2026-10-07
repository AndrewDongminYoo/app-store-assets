# Shared Store Runtime Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans inline, with one implementer. The user approved the linked design and phased sequence; continue without another approval round.

**Goal:** Replace home-owned execution with a pinned repository package, fail closed on the reviewed transfer defects, and prove a Mirae clean-clone fixture workflow.

**Architecture:** Keep the existing image CLI; add small standard-library modules for records, identity, planning, snapshots, generation, execution and command adapters. A consumer verifies its Git dependency before importing it. Remote effects use an explicit provider protocol and immutable staged inputs.

**Tech Stack:** Python standard library, Ruby/Fastlane 2.240.1, ImageMagick 7, optional oxipng.

**Spec:** `../specs/2026-10-07-app-store-assets-design.md` (approved 2026-10-07 15:39 UTC); phased sequence is maintained in the workspace review documents.

## Global Constraints

- One implementer; no source/doc/fixture/asset copying from Cami or other consumers.
- Reuse implementation only from Mirae and app-store-assets.
- Original dirty repositories, HEADs and untracked inputs remain untouched.
- No actual store authentication/transfer, credential reads or creation, public publication, visibility change, app release, PR or push.
- Standard library; no service/database/capture framework. Preserve originals and old bundles.
- Pin source URL, full commit and complete executable inventory/hash; no home/sibling fallback.
- Imported/widget images never become native capture evidence by matching a commit.
- Byte reproducibility is scoped to one locked toolchain; signed exports record actual bytes.

## Review Focus

- Path escape, symlink and shell metacharacters: reject escaping inputs and use argv arrays.
- Omitted/added helper or changelog: invalidate the approved digest before any provider effect.
- Account/app/flavor/version conflict: block before the first write, including stale remote IDs.
- Cache tampering/concurrent execution: validate immutable records and retain failed/pending attempts.
- Provider stdout/private fields: allowlist public snapshot fields; no raw credential/error echo.

## Task 1: Stop the legacy approval bypass

**Files:** modify `lib/fastlane_assets.rb`; create `tests/test_bridge.py`; update existing opt-in bridge integration expectations.
**Interfaces:** `AppStoreAssets.prepare` fails before preparation/transfer; `prepare_local` returns only local paths. Guarded execution goes through the consumer launcher and reviewed plan.

- [x] RED: `test_legacy_prepare_cannot_enable_replacement` asserts nonzero Ruby result and zero external calls for a synthetic legacy consumer.
- [x] Run `python3 -m unittest discover -s tests -p test_bridge.py -v`; expect an assertion failure on the old successful prepare route.
- [x] Implement fail-closed bridge and explicit local-only preparation.
- [x] Run the bridge tests and full suite; expect pass with opt-in integrations skipped.
- [x] Commit candidate-only fix; record evidence in the ledger.

## Task 2: Bind profiles, runtime and all declared inputs

**Files:** `app_store_assets/{__init__,records,identity,profiles,planning}.py`, `schemas/profile-v1.json`, `tests/{pipeline_support,test_planning}.py`.
**Interfaces:** `inventory(root, paths) -> dict[str,str]`; `runtime_identity(root,pin) -> dict`; `load_profile(root,path,target) -> dict`; `make_plan(root,profile,target,operation) -> dict`; `verify_plan(root,plan) -> None`.

- [x] RED: tests reject changed/added Fastfile, guard, changelog, full runtime and target mismatch; offline planning cannot invoke subprocess/store callbacks.
- [x] Run `test_planning.py`; expect absent new interface/unsupported command failures.
- [x] Implement canonical records, strict paths/profile, Git+inventory integrity and content binding.
- [x] Verify inventory mutation, unknown config keys, development binary block, paths with spaces/metacharacters and full suite.
- [x] Commit candidate-only contract implementation.

## Task 3: Guard exact-target execution and immutable staging

**Files:** `app_store_assets/{execution,providers}.py`, `tests/test_execution.py`.
**Interfaces:** provider `snapshot(target)`, `upload(plan,staged_root)`, `readback(plan)`; `execute(root,plan,digest,provider,state) -> receipt`.

- [x] RED: fake provider replaces the original AAB during lookup; upload must observe reviewed staged bytes. Two Apple editable versions must select the exact planned ID. Remote-only classes, revision drift, environment overrides, partial failure and duplicate attempts must block/persist correctly.
- [x] Run `test_execution.py`; expect missing executor failures.
- [x] Implement staging-before-preflight, precise snapshot binding, target lock, receipts and pending readback.
- [x] Run all tests; verify zero remote writes for invalid/dry-run plans and target-specific readback.
- [x] Commit candidate-only executor.

## Task 4: Versioned snapshots and metadata diffs

**Files:** `app_store_assets/{snapshots,metadata}.py`, `tests/test_snapshots.py`, `schemas/records-v1.json`.
**Interfaces:** `publish_snapshot(root,record,files) -> path`; `validate_snapshot(path) -> record`; `metadata_diff(before,after) -> list`; `download_snapshot(provider,target,state) -> path`.

- [x] RED: preserve edited local metadata/changelogs during download, reject private fields/export, reject changed caches, preserve ordering and target/version conflicts.
- [x] Run targeted tests; expect missing snapshot interfaces.
- [x] Implement immutable content-addressed publication, explicit public metadata normalization/diff and read-only provider protocol.
- [x] Run snapshot concurrency/cache tests and suite.
- [x] Commit candidate-only snapshot support.

## Task 5: Image rules and locked generation

**Files:** `app_store_assets/{catalog,generation}.py`, `catalog/store-rules-v1.json`, `tests/test_generation.py`.
**Interfaces:** `validate_images(root,entries,store) -> list`; `toolchain() -> dict`; `generate(root,recipe,state) -> snapshot`.

- [x] RED: same locked toolchain generates identical final records/bytes; source/helper/font/tool changes invalidate generation; hidden/format/alpha/count/slot violations fail; no capture provenance upgrade.
- [x] Verify official Apple/Google rules and record URL/date; implement supported slots only, using ImageMagick decoding and fixed normalization.
- [x] Run real local ImageMagick generation with synthetic images, no external capture/store calls.
- [x] Verify no original modification and full suite; commit candidate-only generation.

## Task 6: CLI, command/build/provider adapter boundaries

**Files:** `app_store_assets/{cli,commands,builds}.py`, `assets.py`, `lib/store_provider.rb`, `tests/{test_cli,test_builds,test_provider}.py`, `examples/`.
**Interfaces:** commands receive canonical JSON via stdin and return bounded JSON; `build(root,target,adapter,state) -> build_record`; CLI exposes doctor/plan/diff/generate/build/download/execute/verify with explicit effect flags.

- [x] RED: dry-run cannot launch adapters, inherit store credentials or use mixed legacy build/upload; command paths and outputs are bound and native artifact identities agree.
- [x] Implement argv-only command execution, sanitized local environment, explicit remote opt-in, Fastlane adapter guards and truthful capability blockers.
- [x] Test actual pinned Fastlane reader plus fake external boundaries. Unsupported Toss/Steam/browser/OTA operations remain explicit blockers until a reviewed adapter is supplied.
- [x] Run suite/Ruby syntax and commit candidate-only CLI/adapters/docs.

## Task 7: Mirae pinned clean-clone pilot

**Files (isolated Mirae):** `store-upload`, `store-upload.json`, `scripts/store_assets/{build,artwork}.py`, `scripts/test_store_assets.py`, `docs/notes/store-assets.md`, dependency gitlink/manifest.
**Interfaces:** launcher verifies URL/commit/full inventory before importing CLI; actual production/staging/development identities stay in Mirae; app-specific composer stays owned by Mirae.

- [ ] RED: fresh consumer clone without home/sibling state runs offline plan; altered dependency, artifact/native identity and helper/changelog fail; fixture transfer uses exact staged paths.
- [ ] Integrate dependency and build-only/artwork adapters in isolated Mirae, including originally untracked required configuration in candidate commits.
- [ ] Prove fixture workflow generate/build-record -> snapshots/diff -> plan -> fake target preflight -> upload -> readback from clean clones. No signed build/device run.
- [ ] Commit only candidate consumer changes; retain full clean-clone evidence.

## Task 8: Review, checks and handoff

**Files:** operational docs, CI, runtime inventory, `docs/notes/2026-10-07-implementation.md`.

- [ ] Self-review each contract/diff and pin all new executable/schema/catalog inputs.
- [ ] Run entire suite, opt-in real Fastlane reader, Ruby syntax, Git diff checks and clean-clone pilot.
- [ ] Compare original Mirae/app-store-assets state/hashes with baseline.
- [ ] Report implemented capabilities, candidate commit/path, remaining provider/signing/device validations, LICENSE and separate PR/push authority. Do not merge/push/publish.
