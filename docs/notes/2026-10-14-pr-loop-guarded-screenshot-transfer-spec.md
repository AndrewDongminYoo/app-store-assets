# PR loop: guarded screenshot transfer specification (2026-10-14)

Pull request #30 (`docs(specs): define the guarded screenshot transfer contract`, for issue #28) was closed by the review loop's round limit.
The branch `feat/guarded-screenshot-transfer-spec` is kept; its last pushed head is `063b4e3`, and `da98e91` (the round-six fix) is committed locally only.

## Stop signal

Six hosted review rounds on a public repository, against a limit of more than five.
Before the pull request opened, the build workflow's review fixed three issues and three local Codex rounds fixed four more, the last local round finding none.

## Rounds

| n   | Reviewed head | Findings                  | Disposition         | Fix commit | Files changed by the fix |
| --- | ------------- | ------------------------- | ------------------- | ---------- | ------------------------ |
| 1   | `9c673fc`     | 6 (Codex 2, CodeRabbit 4) | 6 fixed             | `ecd2bd0`  | spec, plan               |
| 2   | `ecd2bd0`     | 1 (Codex)                 | fixed               | `f8cac0d`  | spec, plan               |
| 3   | `f8cac0d`     | 2 (Codex)                 | fixed               | `7e22296`  | spec, plan               |
| 4   | `7e22296`     | 1 (Codex)                 | fixed               | `6a97dc3`  | spec, plan               |
| 5   | `6a97dc3`     | 3 (Codex 1, CodeRabbit 2) | 1 rejected, 2 fixed | `063b4e3`  | spec, plan               |
| 6   | `063b4e3`     | 1 (Codex)                 | fixed, not pushed   | `da98e91`  | spec                     |

"spec" is `docs/specs/2026-10-14-guarded-screenshot-transfer.md` and "plan" is `docs/plans/2026-10-14-guarded-screenshot-transfer.md`.
Round one went through the `pr-round` workflow; rounds two to six were handled inline.
The rejected finding claimed that `create_app_screenshot_set` requires `client:`; Spaceship 2.240.1 defines it as `client: nil`.

## What did not converge

Round one found contract gaps (build binding, absent sets, the writer window, the processing wait, standard output).
Rounds two to six were almost all about the executor's step ordering and Spaceship's waits and retries: when a no-change group must be healthy, what the writer window covers, the creation retry timeout, when image bytes are hash-checked, the upload request timeout and what the lock covers.
At least one fix opened the next gap: round four limited byte staging to uploading groups, and round six found that no-change groups were then classified from unchecked bytes.
Each finding was valid against the installed fastlane 2.240.1 source, so the rounds did not fail on false positives; the surface was large enough that each pass found one more ordering detail.

## Alternative

Narrow the specification to the binding invariants: the approval record bound to the whole plan target, declared groups as the listing's actual pairs, no remote write until every check (including every image's SHA-256) passes, every wait bounded, and readback or fail.
Move step ordering, Spaceship timeout settings and retry budgets into the U4 acceptance tests, where the fake's call log enforces them, instead of prose that each review pass can find one more gap in.
The other option is to reopen #30 with `da98e91` pushed and merge it as it is, treating the remaining precision as U3 and U4 test work.

## Outcome

The operator chose the narrower specification on 2026-10-14.
It replaces the first draft on the branch `feat/guarded-transfer-invariants`, and the round-six fix (`da98e91`) is carried as invariant 2 there.
