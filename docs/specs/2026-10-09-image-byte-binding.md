# Image byte binding for offline validation

The final independent review of B1 8bd53e6 and B2 04c2665 reproduced a metadata
snapshot which combined the original image SHA with dimensions decoded from a
temporarily substituted image. A later pathname hash saw the restored original.
B2 could export the original 512x1024 PNG with remote.size [1,1].

Acceptance: shared image decoding consumes the same bounded bytes whose digest
matches the caller's reviewed inventory. Decode through stdin rather than
reopening a mutable decoder input file. Snapshot, catalog, local publisher and
export signature checks must use this common byte contract. Replacement and
restoration between inventory, capture and decode must reject or retain the
semantics of the captured bytes; it may not combine different captures.

Keep public PNG/JPEG signature/name/extension rules, 64 MiB image bounds, existing
ImageMagick, complete record validation and no-follow input access. B1 has no
writer implementation. B2 retains exactly the same reader bytes. No native
capture system, dependencies, provider/store calls, credentials, consumer pins,
Mirae transfer or C/D/E functionality is added.

Authority: Sentinel_a0e39ae66ff0819180b97a50701f69aa, 2026-10-09 21:56:06 UTC.
One common repair pass and one independent final confirmation, no further local
repair loop. Normal PR publication is authorized; unresolved defects or
nonconvergence require Draft. B2 may target the B1 branch to expose its writer-only
diff, then must update onto main and retest before merge. No merge or auto-merge.

Historical source PR3 and PR5 remain open; old branches, commits and proofs stay
intact. Hosted rounds PR3=9/A=2/B=2 and independent local review jobs=5 remain
spent. The new confirmation is one additional job, not an accounting reset.
Each new PR gets at most one hosted confirmation round and a 60-minute review
deadline. No hosted repair passes are budgeted. Missing/failed CI or reviewers
are not passes. The PR3-only CodeRabbit waiver does not transfer here.

Existing six Ttush safety failure reports remain visible; native/signing/actual
transfer and live remote freshness remain unverified. No visual product output
is changed by this parser/validation fix; operator visual judgment is inapplicable.
