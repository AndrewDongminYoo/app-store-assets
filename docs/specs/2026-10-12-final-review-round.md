# Final review round for PR6 and PR7

The operator approved one more bounded repair round on 2026-10-12 for the findings left open at PR6 `cc2e2d1` and PR7 `e6c6e1e`.
It supersedes the earlier "no further repair" boundary in both PR bodies; merge still requires clean exact-head gates.
The same day the operator approved a second round, for the gaps found at PR6 `9ab4763` and PR7 `22e8207`, and set a total image entry limit; the sections below state the contract after both rounds.

## Image platform contract

`validate_images(root, entries, store, platform)` takes the target platform as a required argument.
It rejects any platform the frozen catalog has no slots for (`macos` today) before any decode.
Every image-validation path passes the platform: offline image plans, the snapshot reader, local import and snapshot publication.
Text-only metadata for `macos` stays supported.

Asset manifests and image plans accept only `unverified-import` provenance.
No capture-time build evidence is bound in this package, so a `widget-rendered` label alone is rejected (AGENTS.md: an imported image is never promoted without that evidence).

One `validate_images` call decodes each content hash once.
Every entry still gets its own name, extension, hash, slot and count checks.
One listing, asset manifest or `validate_images` call holds at most `IMAGE_ENTRY_LIMIT` (2000) image entries, checked before any entry is read.
The value is 40 locales at the frozen catalog's 50-image Apple maximum per locale.
Distinct decodes cannot exceed entries, so the same limit bounds them.

## Changelog content bases

Changelog resolution never infers a snapshot from a directory name.
A snapshot content root that a caller passes is validated by that caller first.
A record's `source_snapshot` is a provenance pointer, never a source of notes.
It must name a `manifest.json` whose snapshot holds a `metadata-snapshot` or `metadata-import` record for the same target; that snapshot is validated and its inventory bound, so plans list its files as inputs.
A record that names `source_snapshot` keeps its release notes inline and may not carry `changelogs`.
This replaced an earlier rule in the same round that let the named snapshot vouch for changelogs below it; each version of that rule drew a new hosted finding, so the special case was removed rather than guarded again.
Snapshot changelogs read through an explicit snapshot content root still follow contract 1 of `2026-10-09-additional-input-bindings.md`.

## Google release notes and CLI status

A Google record whose releases do not include the target build keeps its top-level notes.
A release that includes the target build still rejects conflicting notes.
The reader CLI and PR7's local write CLI print one line and exit with status 2 for subprocess timeouts and `RecursionError`.

## Local publication (PR7)

Export decodes each image's pixel stream once per content hash before it publishes the editing tree.
An existing snapshot winner is validated under `total_limit=FILE_LIMIT`.
An imported listing keeps its release notes inline and names its history snapshot only as `source_snapshot`; it writes no `changelogs`.
Local snapshot publication rejects records that carry `changelogs`.
Export resolves a metadata snapshot's `changelogs` against that snapshot, so their notes are exported and a reference missing from the snapshot inventory rejects before any output.
