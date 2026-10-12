# B1/B2 local public input contracts

Approved by Sentinel_ec09f37b27008191a451f5d13a7cc025 at 2026-10-09 14:50:28 UTC.
Base A/main: 542840600d8f6ee006d1e9936f7f4fe816cbc6e2, remotely rechecked.
Reference only: PR5 e34b3349032cb84a014138f31cf3bb625c38bac9.

B1 distributes only doctor/plan/diff and their shared public-input, profile,
record, catalog, artifact/image validation and snapshot reader. It contains no
import/export/staging/publisher implementation or eager writer import. B2 is a
separate local dependent branch adding explicit local import/export/staging and
the publisher. It will be posted against main only after B1 merges, following
an authorized rebase/update and complete exact-HEAD verification. No publishing
or PR change is authorized by this local implementation approval.

Every public file is opened without following any component symlink; private
name patterns apply to every relative component before access. JSON/text/image
and artifact classification consume bounded captured bytes. Parsed/validated
digests bind final inventory. No pathname re-open can escape confinement.
Source directory traversal uses directory descriptors with no-follow checks.

Every serialized or published record is fully typed, including nested values,
target identities, public URLs, provenance, source/export digests and runtime
inventory. Unknown keys fail closed. Metadata URL queries are limited to public
language selectors `lang`, `hl`, `locale`, with locale-shaped values; fragments
are rejected. Runtime origin URLs accept HTTPS without query/userinfo/fragment.
These offline policies are explicit acceptance rules, not live store promises.

Typed validation applies to raw or snapshot inputs and to the final object after
adding fields. Hash/address verification does not replace semantic validation.
B2 validates export header/entry schemas before manifest-directed access, and
validates final metadata/asset history records before creating output/history.
Dry-run performs all selected validation with no durable writes. Publishers
reserve only new destinations, preserve prior snapshots and validate winners.

APK and AAB remain supported; kind/extension/container/target/hash binding stays.
IPA remains an offline iOS container. Native/signing identity and supplied
remote freshness remain unverified. No C/D/E, provider, store, account, signing,
device, consumer changes or credential access. Stdlib and existing ImageMagick
only. Preserve A production/legacy tests and the six existing Ttush reports.

Track all six PR5 P2 IDs: 4230952487, 4230952491, 4230952497, 4230952504,
4230952509, 4230952512. They remain unresolved on PR5; local evidence is separate.
Preserve PR3 nine / A two / B two hosted rounds and old proof hashes. New local
split does not waive gates or grant/reset hosted review budget.

Each slice gets one independent local whole-candidate review, with at most one
verified repair pass by the root. Report the exact reviewed and final SHAs and
any resulting independent-review gap. Do not use repeated reviews as discovery.

Compatibility: public helper signatures may become stricter to make the safe
read contract real. Trusted entry roots are canonicalized once; untrusted child
paths are never resolved through symlinks. B1 fixture construction uses test-only
snapshot writing so writer code is absent from its actual distribution.
