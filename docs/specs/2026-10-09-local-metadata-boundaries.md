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

Outputs use no-follow directory descriptors for every parent and component.
New file links and exclusive directory renames avoid replacing existing outputs.
Immutable ancestors forbid writes into old snapshots. Directory publication uses
Darwin `renameatx_np(RENAME_EXCL)` or Linux `renameat2(RENAME_NOREPLACE)` through
stdlib ctypes and fails before writes on unsupported systems. Concurrent existing
winners require a complete typed snapshot/address/hash/inventory match. A local
snapshot or stage caps total captured content at 1 GiB; individual images cap
at 64 MiB and public text at 8 MiB. Read-only mode bits are supplementary; typed
address/hash checks remain authoritative if an owner changes permissions.

Local interruption can leave new validated history without a final listing;
prior snapshots and existing editing trees are preserved. Import is not a
cross-directory transaction, store upload, or release executor. Provider/account,
native/signing and remote freshness remain unverified.

Publication is not authorized. B2 must wait for B1 merge, update/rebase onto
current main, and undergo exact-head local/CI/review gates under separately
approved publication/review budget. No stacked hosted waiver. PR3/5 and their
existing budgets/states stay unchanged; this split does not reset them. B1/B2
each get one independent local whole-candidate review and at most one root
repair pass, with reviewed versus final SHAs and gaps disclosed.
