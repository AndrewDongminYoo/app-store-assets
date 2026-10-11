# Import resource and preservation guards

The operator approved this bounded follow-up on 2026-10-11 together with the reader parser resource repairs.
The existing stacked PRs remain the delivery units: reader resources in PR 6, local import preservation and budgets in PR 7.

Import rejects either-direction overlap between its editing source and listing or history root before any publication.
This includes an editing source underneath `state/metadata` or `state/assets`, where a predicted immutable snapshot would otherwise alter the source tree.
Both dry-run and publication use the same guard.

The exact editing tree is enumerated through no-follow directory descriptors without hashing undeclared files.
Every declared regular file is reserved before any inventory hash: manifest, fields and notes at 8 MiB each, images at 64 MiB each, and their combined input at 1 GiB.
Metadata-only still applies image reservations and source hashes although it omits image publication.
Hash reads reopen through the public no-follow reader, require the reserved file identity, read no more than the reserved size plus one byte, and recheck identity after the read.
The complete bounded inventory is repeated before publication to detect changes and extra files.

The hosted confirmation exposed two further defects in these preservation and pre-capture guards.
Apple top-level selected notes now become the exported `release_notes.txt` field and return to both fields and selected notes on import; identical duplicate representations coalesce and conflicting values fail before publication.
Direct snapshot publication now preflights its output root before retaining any path source or decoding images, and repeats that preflight before publication to retain race protection.
These repairs share the bounded second candidate with the ZIP64 compatibility correction; they do not open another review scope.

Staging opens its source root through no-follow descriptors even for an empty inventory.
This closes the reproduced alias case that bypassed all file reads and published an empty directory inside the real source.
Nonempty inventories already rejected this source alias during capture.
Resolved paths supplement the lexical overlap check; unresolved paths remain authoritative for no-follow I/O.

## Completion criteria

- Both reserved history ancestors reject import in dry-run and publication without changing source bytes or directory contents.
- Text, image and aggregate overflows reject before any inventory hashing, including metadata-only imports.
- Exact input capacity succeeds; undeclared files reject without hashing them.
- Empty staging through a source symlink rejects without creating output.
- Apple selected notes survive export/import, including empty notes; conflicting duplicate values reject both real and dry-run export.
- Invalid private, symlinked or immutable snapshot output roots reject before path capture and image validation.
- CI documentation agrees with `main` and `split/offline-read-boundaries` workflow filters.
- Full unit tests, Ruby syntax, scoped lint, independent review and pushed-SHA hosted gates are recorded.

PR 7 receives PR 6 through a normal merge to preserve history without force push.
The previous stopped review history remains recorded.
This approved continuation has the same bounded candidate and deadline policy as the parser-resource specification.
Computer Use, store operations, private SDK execution and billing remain excluded.
