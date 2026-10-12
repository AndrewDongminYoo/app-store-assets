# Final review round for PR6 and PR7

The operator approved one more bounded repair round on 2026-10-12 for the findings left open at PR6 `cc2e2d1` and PR7 `e6c6e1e`.
It supersedes the earlier "no further repair" boundary in both PR bodies; merge still requires clean exact-head gates.

## Image platform contract

`validate_images(root, entries, store, platform)` takes the target platform as a required argument.
It rejects any platform the frozen catalog has no slots for (`macos` today) before any decode.
Every image-validation path passes the platform: offline image plans, the snapshot reader, local import and snapshot publication.
Text-only metadata for `macos` stays supported.

One `validate_images` call decodes each content hash once.
Every entry still gets its own name, extension, hash, slot and count checks.
Distinct images still cost one decode each, and the total entry count has no separate cap.

## Changelog content bases

Changelog resolution never infers a snapshot from a directory name.
A snapshot content root that a caller passes is validated by that caller first.
A record that names `source_snapshot` must name a `manifest.json`, and that snapshot is validated and its inventory bound before any changelog is read.
So a changelog below an imported listing's history snapshot must match that snapshot's inventory (contract 1 of `2026-10-09-additional-input-bindings.md`).

## Google release notes and CLI status

A Google record whose releases do not include the target build keeps its top-level notes.
A release that includes the target build still rejects conflicting notes.
The CLI prints one line and exits with status 2 for subprocess timeouts and `RecursionError`.

## Local publication (PR7)

Export decodes each image's pixel stream once per content hash before it publishes the editing tree.
An existing snapshot winner is validated under `total_limit=FILE_LIMIT`.
