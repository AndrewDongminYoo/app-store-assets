# B1/B2 Input Boundary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. The root implements inline; one independent whole-slice review per B1 and B2, sequentially.

**Goal:** Prepare independently reviewable local read-only and local-write slices with complete public input contracts.

**Architecture:** B1 owns confined input, full typed records and snapshot reading plus doctor/plan/diff. B2 depends on B1 and alone supplies metadata I/O, staging and snapshot publication. Shared validation runs on the exact final record, not only a subset before provenance enrichment.

**Tech Stack:** Python stdlib, existing ImageMagick 7, existing Ruby/Fastlane stub harness.

**Spec:** `review/SPLIT-B12-SPEC.md`; boundary matrix `review/SPLIT-B12-BOUNDARY-MATRIX.md`.

## Global Constraints

- Local audit/implementation/tests/commits/PR draft only; no remote mutation or new hosted budget.
- Preserve A/PR3/PR5 branches, old proof bytes, original note/stash and held Mirae pin.
- APK/AAB/IPA containers remain offline; native/remote authenticity unverified; no C/D/E.
- All tests synthetic/temporary or copied public Fastfiles with external actions stubbed and networking blocked.
- One independent local review per slice, one root repair pass; no repeated empty reviews.

## Review Focus

- Parent directory replaced after lexical validation: no outside byte read through hash/text/image/copy.
- Direct private-parent descendant: reject before file or directory access.
- Final provenance enrichment after an earlier validator: exact published record must be validated.
- Nested unknown/private values in every supported record, profile and runtime descriptor: reject before output.
- Mutable input after parse/classification: captured digest and serialized value remain bound at all entry points.

### Task 1: Preserve baseline and demonstrate boundaries

Files: new evidence/ledger, tests/test_offline_boundaries.py, tests/test_metadata_write_boundaries.py.
Interfaces: existing e34b334 APIs; fixtures contain only synthetic public values.
- [ ] Freeze old proof hashes and verify current main/A and source/Mirae states.
- [ ] Write six mechanism and cross-entry regressions before product changes.
- [ ] Run against e34b334 in temporary copy: expect assertion failures for all six, not harness import errors.
- [ ] Write B1 distribution test: expect writer files/commands present in the reference and absent after extraction.

### Task 2: B1 confined input and typed read contracts

Files: records.py, contracts.py, record_types.py, profiles.py, metadata.py, artifacts.py, catalog.py, snapshots.py, planning.py, cli.py; B1-owned tests/spec/matrix.
Interfaces: open_read(path) yields a regular-file stream opened by no-follow component traversal; capture_bytes(path, limit, captures) returns the exact bounded bytes and binds their SHA; typed validators return validated public records; snapshot reader validates supported nested record.
- [ ] Run Task 1 reader regressions RED, including helper and CLI routes.
- [ ] Implement descriptor-safe reads/hash/directory inventory and all-component private checks; migrate direct input opens.
- [ ] Implement full typed schemas and URL policies; validate records before plan/diff serialization.
- [ ] Extract reader distribution and migrate writer assertions to B2 tests without dropping them.
- [ ] Run reader regression GREEN and full default/SDK/personal gates; expect only known Ttush six reports in personal.
- [ ] Commit B1, independent whole-candidate review, one TDD repair pass if needed, exact final verification.

### Task 3: B2 local writes and final publication contracts

Files: metadata_io.py, publisher.py, staging.py, write_cli.py; B2-owned tests/spec.
Interfaces: B1 public input/record validators; B2 new-only output reservation and typed publisher using safe directory descriptors.
- [ ] Create local B2 branch/worktree from verified B1 commit.
- [ ] Run import/provenance/dry-run and parent-race copy regressions RED on reference behavior.
- [ ] Validate mutable export manifest before access and final metadata/asset records before writing.
- [ ] Capture/copy via safe descriptors, separate writer CLI with no eager B1 dependency on writer code.
- [ ] Run full gates and round-trip/winner/dry-run regressions GREEN; retain consumer failures.
- [ ] Commit B2, independent whole-candidate review, one TDD repair pass if needed, exact final verification.

### Task 4: Final local delivery

- [ ] Export both exact commits and patches with per-file hashes; retain regression RED/GREEN and reviewed/final SHAs.
- [ ] Prepare local PR drafts: B1 against current main; B2 against main after B1 merges and authorized update/retest.
- [ ] Verify old proof hashes/source/Mirae/branch refs; clean only task-owned worktrees when safe.
- [ ] Report matrix, six finding mappings, test method pass/skip/subcase counts, independent review limits and no hosted waiver/reset.
