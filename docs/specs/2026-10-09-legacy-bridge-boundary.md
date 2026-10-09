# Legacy screenshot bridge boundary

This is extraction A from the non-convergent shared pipeline PR3, based on the existing screenshot-bundle main branch.
It introduces no `app_store_assets` package, pipeline command dispatch, schemas, authentication, native build or store transport.

## Contract

`AppStoreAssets.prepare` must fail before spawning any local preparation process or returning options to a transfer lane.
Its failure states that a reviewed plan and digest are required for transfer, without claiming that this unit provides such an executor.
`AppStoreAssets.prepare_local` is explicit local preparation and returns the existing validated bundle path without an overwrite flag.
Source images and previous bundles remain unchanged, and existing bundle validation/cache tests still pass.
This is an intentional fail-closed compatibility change for callers of the legacy transfer bridge.
Callers that upload through their own direct Fastlane invocation require separate consumer changes.

## Verification and limits

The legacy-block and local-preparation regressions fail on the unchanged main bridge before extraction.
An intercepted `Open3.capture3` regression requires zero process calls for the blocked legacy method.
The default suite and Ruby syntax check must pass.
The installed Fastlane 2.240.1 reader check must pass without store activity.
Actual personal Fastfiles are copied to temporary repositories, Mirae's public helper is copied with its Fastfile, and only external actions are stubbed.
The fixture blocks sockets and native/store process launches and uses an isolated home.
Mirae and Kkom negative/metadata-only cases must pass; Ttush's six pre-existing safety failures remain explicit and are not skipped or weakened.
The replacement of old positive-upload assertions with legacy-block assertions follows the changed contract; local image-validation tests remain intact.

## Extraction and review boundary

This unit carries PR3's existing shared legacy bridge safety fix, not its six unresolved source fixes.
PR3 and its branch/evidence remain preserved, with nine cumulative hosted rounds and no hosted requests for this local extraction.
Current unresolved source work belongs to later offline validation, immutable generation and guarded transport units.
One local implementation pass, one independent read-only review and at most two necessary local repair passes bound this unit.
Any cross-domain blocker returns to the parent; publication and PR3 closure/replacement remain separately authorized.
