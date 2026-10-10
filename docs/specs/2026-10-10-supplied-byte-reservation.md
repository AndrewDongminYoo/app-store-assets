# Supplied-byte reservation repair

The parent delegation from thread 01a118cd-16f4-72d9-aadd-5cfdf9a66024
extends the earlier parent-defined two-head tranche by one changed B2 head
and 60 minutes, starting 2026-10-10 00:24:45 UTC. Preserve the previous
tranche, commits, reviews and evidence. The cumulative additional B2
published-head allowance is three; this repair uses at most one new head.
No new PR, merge, deployment, consumer or runtime pin change is authorized.

Fix hosted P2 4235551221 on B2 1899b8074094b9f18d5df6ef02920c8549799c54.
Before reading any path-backed content, validate and charge every supplied
byte entry against the aggregate capture budget, including each image's
individual limit. Capture path entries only with the remaining aggregate
budget and the existing image limit. Input mapping order must not change
that reservation. An oversized supplied total/image rejects before any
path read or durable output. Exact aggregate and individual bounds remain
accepted for valid content. Existing typed record/hash/address/winner,
no-follow, serialization and durable-publication validation remain intact.

Regressions cover mixed entry permutations, supplied-total overflow,
oversized supplied images, exact valid aggregate/image bounds and retained
path limits. Use scaled synthetic limits in guarded copies rather than
large allocations. Run unchanged default, SDK and opt-in personal suites;
record suite exit codes and baseline differences explicitly. Preserve the
byte-identical B1 shared reader/bridge/workflow files. Independently review
the exact committed candidate and the same aggregate/per-image boundary,
then normal-push the existing stacked PR and verify exact-head CI/reviews.
A different-domain or new material defect returns to the parent.

The integration contract in legacy-bridge-boundary.md requires Mirae/Kkom
negative and metadata-only cases to pass and Ttush's six pre-existing
safety failures to stay explicit without skips or weakened assertions.
public-input-boundaries.md also says to preserve those six reports and
excludes consumer changes. Their opt-in suite remains FAILED; an unchanged
baseline is evidence of a separate consumer defect, not a new B1/B2 defect
or a zero-failure integration pass. This package approves no store transfer
or deployment. Any new integration failure or changed baseline is a blocker.
