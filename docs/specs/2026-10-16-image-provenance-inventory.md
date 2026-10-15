# Image Provenance Inventory

This correction implements [issue #40](https://github.com/AndrewDongminYoo/app-store-assets/issues/40).
The offline image plan must bind the complete metadata provenance snapshot that it validates, including directory membership at the final inventory pass.

## Problem

`resolve_changelogs` validates a listing's `source_snapshot` and captures its existing files.
Image planning adds those captured files to its final inventory, but does not inventory and compare the provenance directory itself.
A file added after snapshot validation can therefore escape the snapshot membership check.
The existing `doctor` path already checks this boundary.

Adding snapshot directories also overlaps with declared inputs and captured child paths.
The final inventory must charge each file once without allowing a missing declared child to disappear behind an ancestor directory.

## Contract

- Image planning inventories the listing's metadata provenance snapshot directory and compares its complete final file inventory with the validated capture.
- The check applies whether or not the target declares an asset manifest.
- Asset snapshot membership and captured-byte comparisons remain enforced.
- Overlapping ancestor and descendant paths share one final inventory traversal per covered file.
- A requested file or directory that is absent before or after that traversal still refuses the plan.
- The plan retains its declared input paths, `executable: false`, `effects: []`, and supplied-snapshot freshness limitation.

## Scope

Keep the correction in image planning and its regression tests.
Do not change metadata or binary planning, the doctor contract, provider behavior, snapshot formats, dependencies, or consumer Fastfiles.
No command in this work accesses a store.

## Acceptance

1. Inject an undeclared file into the metadata provenance snapshot immediately before final inventory.
   Image planning refuses it with and without a declared asset manifest and with an overlapping declared ancestor.
2. With the aggregate byte allowance set to the exact total of the fixture's distinct inputs, image planning succeeds for overlapping ancestors and descendants.
   One byte less still refuses the plan.
3. Missing declared children and removed empty directories remain rejected when an ancestor covers their paths.
4. The default regression suite passes and the existing doctor regressions remain green.
   Report the separately tracked Mirae integration failure under #41 without changing that fixture here.
