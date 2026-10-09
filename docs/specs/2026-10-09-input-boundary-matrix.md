# Input boundary matrix — B1/B2

Required sequence: confined read -> captured bytes/digest -> complete typed
validation -> final hash binding -> serialization/publication. Rows apply to
direct public functions as well as CLI; unavailable operations are rejected
before profile/input access. Reference PR5 remains intact.

| Input/record | Entry points | Required boundary and regression owner |
| --- | --- | --- |
| Public file/directory path | all CLI, records inventory/hash, profile, snapshot, artifact, image, B2 I/O/staging | component private names before access; fd-relative no-follow opens and traversal; parent replacement never reads synthetic outside marker; 4230952509/2512 |
| Profile and all nested targets/runtime/version descriptors | doctor/plan/diff and B2 CLI | exact keys/types incl unselected target shapes; selected version-source captured once; public origin URL; no credential/provider/build recipe values |
| Runtime identity and file hashes | local_context, plan, B2 publication provenance | exact public origin/commit/inventory; executing runtime bytes equal pin; no opaque nested values |
| Metadata/local listing/supplied observation/import history | plan metadata/images, diff raw/snapshot, export reader, import final history | same full public record validator; nested target/binary/release/image/input/provenance types; unknown/private values rejected; URLs before output; 4230952487 |
| Metadata URLs | every metadata normalization/validation path | public HTTP(S), host/port, no auth/fragment, explicit locale query allowlist, decoded/duplicate query checks |
| Build declaration | binary plan, build snapshot reader | exact top-level and native/source/adapter/inspector nested types; fixture/live declarations remain unverified; APK/AAB/IPA kind/hash; 4230952491 |
| Asset manifest/provenance/entries | images plan, snapshot reader, B2 final asset history | complete typed schema before ordered tuple use or output; recomputed image SHA/size; 4230952497 |
| Snapshot envelope/inventory | all snapshot readers and B2 publisher winner | exact envelope/hash/address/inventory plus supported fully typed nested record; directory no-follow; no opaque arbitrary record |
| Catalog/schema bytes | runtime pin, field/image rules | approved runtime inventory binds file; frozen catalog structural types before use; no provider/live acceptance claims |
| JSON/text/changelog | profile/version/listing/remote/build, diff, import | bounded unique-key JSON; finite values; canonical captured digest; no Path re-open; no old parse/new final hash |
| Image/artifact bytes | plan, export/import/staging | bounded captured input, descriptor-safe opens; validate bytes/classification on capture, bind digest to final inventory |
| Mutable export manifest | B2 import API/CLI including dry-run | exact public header/source digest/field/image/note entry schemas before declared-path hashing; 4230952504 |
| Final generated metadata/asset history | B2 import and publisher | validate actual record AFTER source_export/runtime/catalog/provenance additions; invalid record creates no output/history; 4230952504 |
| New outputs/state/staging destinations | B2 export/import/stage/publisher | safe directory descriptors, no ancestor snapshot overlap, new-only reservation; preserve source/editing/history; bounded capture used for copy |
| B1 distribution/import graph | installed B1 package and CLI | import/export/staging/publisher files absent and commands unavailable before any profile read; no writer loaded transitively |

Before product changes, add behavioral regressions for every six reported
mechanisms and cross-entry-point checks. Separate existing reader and writer
tests by behavior; retain all assertions in their owning slice, with a migration
map. Do not skip or remove a failing consumer assertion to make either green.
