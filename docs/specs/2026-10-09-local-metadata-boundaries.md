# Local metadata boundary extension

B2 depends on B1 final 8bd53e682974716d26806b6973dcb9789831ec01. The
app_store_assets reader package stays byte-identical; app_store_assets_local
alone implements import/export, staging and local immutable publication.

CLI: `python3 -B -m app_store_assets_local import|export --root PROJECT
--target NAME --source PUBLIC_PATH --output NEW_PATH`. `--state` selects a local
history directory; `--metadata-only` explicitly omits unsupported image import.
Both real and `--dry-run` routes validate complete input and final enriched
records. Dry-run writes no durable project/output/history files; image decoding
uses owned temporary captures. The CLI rechecks captured profile/version inputs
and runtime approval just before publication. Direct APIs accept an explicit
public target and make no profile/authentication/freshness claim.

Mutable export manifests use exact header/field/image/note entry schemas.
`source_snapshot` is a SHA256 content address; unknown nested annotations are
rejected even in metadata-only mode. Manifest-directed paths are public,
canonical, unique and validated before inventory reads. Text/images are captured
within bounds and must agree with the exact editing inventory. Final asset and
metadata history records include typed source/export hashes, runtime inventory,
catalog hash and explicit `unverified-import` provenance before any durable write.
Final listing, predicted history addresses and output overlaps are also validated.
A listing file cannot be an ancestor or descendant of its predicted snapshot,
or replace either reserved `state/assets` or `state/metadata` directory. Both
dry-run and publication reject this configuration before creating history.

Outputs use no-follow directory descriptors for every parent and component.
New file links and exclusive directory renames avoid replacing existing outputs.
Immutable ancestors forbid writes into old snapshots. Directory publication uses
Darwin `renameatx_np(RENAME_EXCL)` or Linux `renameat2(RENAME_NOREPLACE)` through
stdlib ctypes and fails before writes on unsupported systems. Concurrent existing
winners require a complete typed snapshot/address/hash/inventory match. A local
snapshot, stage, import or export caps total retained public content at 1 GiB;
individual images cap at 64 MiB and public text at 8 MiB. Supplied snapshot bytes
are charged before path reads, and each later capture uses the remaining total
budget. Serialized snapshot manifests, export manifests and final listings also
cap at the reader's 8 MiB before any durable publication. Exactly 8 MiB is accepted.
Read-only mode bits are supplementary; typed
address/hash checks remain authoritative if an owner changes permissions.

The local publisher accepts only metadata, metadata-snapshot, metadata-import
and asset-manifest records. Build publication is excluded until an artifact
publication contract binds the container and inspected build to captured bytes.
B1 can still read a typed build declaration and plan an explicitly supplied
APK/AAB/IPA through its separate artifact inspection and hash binding. A typed
build declaration in a supplied snapshot does not authenticate a native build.

Local interruption can leave new validated history without a final listing;
prior snapshots and existing editing trees are preserved. Import is not a
cross-directory transaction, store upload, or release executor. Provider/account,
native/signing and remote freshness remain unverified.

The later operator approval Sentinel_a0e39ae66ff0819180b97a50701f69aa authorizes
normal PR publication with Draft conversion for blockers/nonconvergence. B2
targets B1's branch for a writer-only stacked diff. Before merge it must update
onto main after B1 merges and repeat exact-head gates. The current CI only runs
PRs targeting main; absent stacked CI is a blocker, not a pass. CodeRabbit's
explicit applicable stacked skip is recorded as skipped, never reviewed.
PR3/5 branches and spent budgets remain unchanged; this publication does not
reset them. The common image-capture defect gets one new repair pass and one
independent final confirmation. No further repair or merge authority is added.
