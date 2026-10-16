# PR3 source disposition

## Decision and evidence baseline

[Issue #49](https://github.com/AndrewDongminYoo/app-store-assets/issues/49) records the documentation follow-up to the [#48 source audit](https://github.com/AndrewDongminYoo/app-store-assets/issues/48).
No required runtime feature was identified for restoration from the closed PR3 pipeline.
Keep the current narrow implementations and preserve the old source as historical evidence until the archive and retirement checks in [#50](https://github.com/AndrewDongminYoo/app-store-assets/issues/50) are complete.
This document neither performs nor claims completion of that archive or branch deletion.

The comparison uses the [retained PR3 tree at `9fc53959e52402f7dbfe6d3fae93560abdd4aa09`](https://github.com/AndrewDongminYoo/app-store-assets/tree/9fc53959e52402f7dbfe6d3fae93560abdd4aa09) and [main at `d162b8297eb7e4be510c281868abb1bcffcaae47`](https://github.com/AndrewDongminYoo/app-store-assets/tree/d162b8297eb7e4be510c281868abb1bcffcaae47).
The [closing record](https://github.com/AndrewDongminYoo/app-store-assets/pull/3#issuecomment-6121446384) explains the original decision to retain `feat/shared-store-pipeline` for later extractions.
GitHub source links below are pinned to those audited revisions.
The audit inspected source and test definitions; it was not a new exhaustive security review or live store test of the historical pipeline.

The [current ownership boundary](https://github.com/AndrewDongminYoo/app-store-assets/blob/d162b8297eb7e4be510c281868abb1bcffcaae47/AGENTS.md#L3-L6) leaves capture and composition in the owning app repositories.
The [current transfer contract](https://github.com/AndrewDongminYoo/app-store-assets/blob/d162b8297eb7e4be510c281868abb1bcffcaae47/docs/specs/2026-10-14-guarded-screenshot-transfer.md#L9-L12) covers Apple iOS screenshots, not general metadata, binary or multi-store execution.
The separately stated future Asset Library direction is unchanged; it does not make PR3's provider architecture a required implementation.

## Module disposition

“Discard” below means do not reintroduce the historical module into main.
It does not mean delete its only surviving source or review evidence.
“Already served” identifies the current responsibility, not compatibility with every behavior of the old orchestrator.

| Historical source | Disposition | Current responsibility or reason |
| --- | --- | --- |
| [generation.py](https://github.com/AndrewDongminYoo/app-store-assets/blob/9fc53959e52402f7dbfe6d3fae93560abdd4aa09/app_store_assets/generation.py#L34-L131) | Validation/publication already served; discard renderer and composer execution | [Bundle preparation](https://github.com/AndrewDongminYoo/app-store-assets/blob/d162b8297eb7e4be510c281868abb1bcffcaae47/assets.py#L103-L168) and [snapshot publication](https://github.com/AndrewDongminYoo/app-store-assets/blob/d162b8297eb7e4be510c281868abb1bcffcaae47/app_store_assets_local/publisher.py#L143) retain final-byte validation and immutable output. App repositories own composition. |
| [builds.py](https://github.com/AndrewDongminYoo/app-store-assets/blob/9fc53959e52402f7dbfe6d3fae93560abdd4aa09/app_store_assets/builds.py#L14-L84) | Discard build execution; retain current record validation | [Build-record validation](https://github.com/AndrewDongminYoo/app-store-assets/blob/d162b8297eb7e4be510c281868abb1bcffcaae47/app_store_assets/record_types.py#L18) checks supplied evidence without running native build/signing adapters. |
| [execution.py](https://github.com/AndrewDongminYoo/app-store-assets/blob/9fc53959e52402f7dbfe6d3fae93560abdd4aa09/app_store_assets/execution.py#L130-L228) | Screenshot-transfer responsibilities already served; discard generic executor | [Approval-bound staging](https://github.com/AndrewDongminYoo/app-store-assets/blob/d162b8297eb7e4be510c281868abb1bcffcaae47/app_store_assets_local/transfer.py#L59-L138), [target locking](https://github.com/AndrewDongminYoo/app-store-assets/blob/d162b8297eb7e4be510c281868abb1bcffcaae47/lib/fastlane_assets.rb#L201-L246), and [writer/readback](https://github.com/AndrewDongminYoo/app-store-assets/blob/d162b8297eb7e4be510c281868abb1bcffcaae47/lib/fastlane_transfer.rb#L3-L115) implement the narrower current contract. |
| [commands.py](https://github.com/AndrewDongminYoo/app-store-assets/blob/9fc53959e52402f7dbfe6d3fae93560abdd4aa09/app_store_assets/commands.py#L18-L162) | Discard | The generic executable/argument capture protocol is not needed by the fixed verifier and Ruby bridge. |
| [providers.py](https://github.com/AndrewDongminYoo/app-store-assets/blob/9fc53959e52402f7dbfe6d3fae93560abdd4aa09/app_store_assets/providers.py#L12-L95) | Discard | The multi-store registry and command provider exceed the current transfer contract. |
| [provider_python.py](https://github.com/AndrewDongminYoo/app-store-assets/blob/9fc53959e52402f7dbfe6d3fae93560abdd4aa09/app_store_assets/provider_python.py#L3-L63) | Discard | Loader for the discarded generic adapter architecture. |
| [provider_ruby.py](https://github.com/AndrewDongminYoo/app-store-assets/blob/9fc53959e52402f7dbfe6d3fae93560abdd4aa09/app_store_assets/provider_ruby.py#L3-L153) | Discard | Loader for the discarded generic adapter architecture. |
| [lib/store_provider.rb](https://github.com/AndrewDongminYoo/app-store-assets/blob/9fc53959e52402f7dbfe6d3fae93560abdd4aa09/lib/store_provider.rb#L173-L200) | Apple screenshot responsibility already served; discard old module | The current writer above handles reviewed screenshot groups. The broader historical Google, metadata, binary and download operations are not required by that contract. |
| [examples/consumer_bootstrap.py](https://github.com/AndrewDongminYoo/app-store-assets/blob/9fc53959e52402f7dbfe6d3fae93560abdd4aa09/examples/consumer_bootstrap.py#L121-L142) | Discard; preserve unresolved finding | Main does not ship this staged-import bootstrap, and no extraction is proposed. See the finding disposition below. |
| [schemas/profile-v1.json](https://github.com/AndrewDongminYoo/app-store-assets/blob/9fc53959e52402f7dbfe6d3fae93560abdd4aa09/schemas/profile-v1.json#L1-L16) | Discard as active schema | The [offline profile](https://github.com/AndrewDongminYoo/app-store-assets/blob/d162b8297eb7e4be510c281868abb1bcffcaae47/schemas/offline-profile-v1.json) replaces the broad recipes/builds profile. |
| [app_store_assets/metadata_io.py](https://github.com/AndrewDongminYoo/app-store-assets/blob/9fc53959e52402f7dbfe6d3fae93560abdd4aa09/app_store_assets/metadata_io.py) | Local import/export already served; do not restore old location | The [local extension](https://github.com/AndrewDongminYoo/app-store-assets/blob/d162b8297eb7e4be510c281868abb1bcffcaae47/app_store_assets_local/metadata_io.py) owns these writes separately from the read-only package. |

The [current offline boundary regression](https://github.com/AndrewDongminYoo/app-store-assets/blob/d162b8297eb7e4be510c281868abb1bcffcaae47/tests/test_offline_cli.py#L58-L71) requires generation, build, command, provider and execution modules to remain absent from the read-only package.
Imported images retain [unverified-import provenance](https://github.com/AndrewDongminYoo/app-store-assets/blob/d162b8297eb7e4be510c281868abb1bcffcaae47/app_store_assets/record_types.py#L116-L119); an app version selection does not establish native capture evidence.

## Tests and historical documents

The following paths refer to the [historical tests tree](https://github.com/AndrewDongminYoo/app-store-assets/tree/9fc53959e52402f7dbfe6d3fae93560abdd4aa09/tests).
Keep their old versions in the archive; do not copy the suite wholesale into main.

| Historical test material | Disposition |
| --- | --- |
| `test_generation.py`, `test_builds.py` | Archive tests of discarded renderer/build execution. Current bundle and provenance tests remain authoritative. |
| `test_adapter_boundaries.py`, `test_bootstrap.py`, `test_commands.py`, `test_execution.py`, `test_execution_locks.py`, `test_provider.py`, `test_store_boundaries.py` | Archive tests of the discarded adapter/transport architecture. The current transfer approval, execution and readback tests cover the supported path. |
| `test_cli.py`, `test_planning.py`, `test_review_boundaries.py`, `test_snapshots.py`, `pipeline_support.py` | Archive the old combined pipeline fixtures and contracts. Current offline/local tests define their separated responsibilities. |
| `test_metadata_roundtrip.py` | Archive the old test version. Current local metadata tests cover the separated import/export implementation. |
| `test_assets.py`, `test_bridge.py`, `test_fastlane.py`, `test_fastlane_reader.py`, `fastlane_harness.rb` | Retain the current main versions; preserve the PR3 versions only as historical evidence. |

The [historical docs tree](https://github.com/AndrewDongminYoo/app-store-assets/tree/9fc53959e52402f7dbfe6d3fae93560abdd4aa09/docs) contains these records:

| Historical document | Disposition |
| --- | --- |
| `specs/2026-10-07-app-store-assets-design.md`, `plans/2026-10-07-shared-runtime.md` | Archive the broad design and implementation plan; do not restore them as an active feature backlog. |
| `notes/2026-10-07-hosted-review.md`, `notes/2026-10-07-implementation.md` | Preserve review and implementation history, including known limitations; earlier verdicts do not approve current code. |
| `notes/2026-10-07-stage-1.md`, `plans/2026-10-07-rollout.md` | Retain the current historical records with this supersession context; remaining app and Asset Library work is not completed by this audit. |
| `specs/screenshot-bundles.md` | Retain the current [local bundle contract](../specs/screenshot-bundles.md). |

Current replacement test evidence is available in [bundle tests](../../tests/test_assets.py), [offline planning](../../tests/test_offline_planning.py), [local snapshots](../../tests/test_local_snapshots.py), [local metadata](../../tests/test_local_metadata.py), [transfer approval](../../tests/test_transfer_approval.py), [transfer execution](../../tests/test_transfer_execution.py), and [transfer readback](../../tests/test_transfer_readback.py).
These local links follow the maintained test files; the pinned source links above define the audit baseline.

## Findings and follow-up boundary

The [bootstrap staging-tree race](https://github.com/AndrewDongminYoo/app-store-assets/pull/3#discussion_r4228068703) remains a historical unresolved finding.
The code is not in main and is not proposed for reuse, so this disposition does not claim to fix it or create a current-main repair task.
Any later proposal to reuse it must reassess that finding against the proposed code.

The [empty unsupported-image-group finding](https://github.com/AndrewDongminYoo/app-store-assets/pull/3#discussion_r4228068708) already has closed [issue #16](https://github.com/AndrewDongminYoo/app-store-assets/issues/16).
The [current regression](https://github.com/AndrewDongminYoo/app-store-assets/blob/d162b8297eb7e4be510c281868abb1bcffcaae47/tests/test_offline_planning.py#L149-L163) requires the empty group to be absent from the plan and rejects a deletion policy that names its unsupported slot.
No duplicate issue or claim of live Google transfer verification follows from that test.

The [documented preparation helper](https://github.com/AndrewDongminYoo/app-store-assets/blob/d162b8297eb7e4be510c281868abb1bcffcaae47/README.md#L121-L219) already publishes final images through the local snapshot API and creates the app-owned listing/profile.
A new packaging CLI is not required by this audit without an observed consumer failure or demonstrated duplication problem.
Missing Google, macOS, binary or capture/build executors are not automatically missing requirements.

Issue #49 completes the source disposition and supersession documentation only.
Issue #50 depends on it and owns a restorable source archive, separate PR discussion evidence, checksum and restoration checks, fresh branch-head/dependency checks, and retirement of the exact retained branch.
The parent #48 remains open until those separate preservation and retirement obligations are settled.
