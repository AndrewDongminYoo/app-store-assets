# App Store Assets

Pinned local coordination for image generation, store rules, immutable asset/build/metadata history, reviewed plans and guarded transfers. Application capture, composition, signing and native release gates stay in their application repositories.

## Requirements and installation

Use Python 3.11+, ImageMagick 7 and Ruby. Optional optimization requires a locked oxipng. The native Apple/Google adapter requires the consumer's frozen Fastlane 2.240.1 Gemfile/lock and an explicitly selected protected authentication file. No Python dependency is required.

A consumer commits `store-upload`, its public `store-upload.json`, app-owned adapters/recipes and a Git submodule. Pin the source URL, full commit and complete executable/schema/catalog inventory. Copy `examples/consumer_bootstrap.py` to `scripts/store_assets/bootstrap.py` and invoke it with `python3 -I -S`. It verifies the dependency before import. Initialize the declared submodule with `git submodule update --init`; there is no home directory or sibling checkout fallback. Runtime/profile/root environment or CLI overrides are rejected.

Local candidates must be reviewed and made available in the declared remote before another machine can fetch their Git pin. This implementation does not publish or release a package. LICENSE remains an owner decision.

## Commands

Commands below run through the application's verified launcher. Targets and public configuration are application owned. Run `doctor` first; it reports capabilities and an **unverified** remote account/target.

```bash
./store-upload doctor --target production-ios
./store-upload generate --target production-ios
./store-upload build --target production-ios
./store-upload diff --target production-ios --before path/to/remote/manifest.json --after path/to/listing.json
./store-upload plan --target production-ios --operation images > reviewed-plan.json
./store-upload execute --target production-ios --plan reviewed-plan.json --expected-digest DIGEST --dry-run
```

`doctor`, `plan`, `diff`, and every `--dry-run` are offline and do not read authentication. Local `generate/build` use sanitized environments and argv arrays. They never call a combined build/upload alias. Live build records require native artifact inspection, successful native guards, current source commit and bound source inputs. The Mirae pilot has a fixture builder; its live signed build path deliberately remains blocked pending a reviewed protected signing/inspection adapter.

Generated and built outputs are content-addressed snapshots. Explicitly review/select their manifest and artifact paths in the consumer profile/listing. Live image plans require `assets: {"manifest": "path/to/snapshot/manifest.json"}`; its target, complete file/locale/slot/hash inventory, provenance and content address must match the listing. The listing's selected image order is bound by the plan and checked at readback; it may differ from generation order. `version_source` resolves the checked-in pubspec version once, including the build number. A `listing` JSON record contains the exact target plus allowlisted localized `fields` and ordered `images` entries (`file`, `sha256`). Google `description` is canonicalized to `full_description` before approval; conflicting aliases are rejected. Preserve original captures, editing trees and older snapshots. Do not promote widget/import provenance to native capture evidence.

Remote operations require operator authority, an explicit account ID, protected auth input and a target. Credentials stay outside public inventories and are read only by the explicitly authorized provider. Download publishes a new snapshot; it preserves local metadata/changelogs. Google reads open and abort an edit/session and **never commit** it; this effect is declared in the snapshot.

```bash
./store-upload download --target production-ios --allow-effects --auth-file /protected/provider-auth.json
./store-upload execute --target production-ios --plan reviewed-plan.json --expected-digest DIGEST --allow-effects --auth-file /protected/provider-auth.json
./store-upload verify --target production-ios --receipt build/store-assets/attempts/ATTEMPT/receipt.json --allow-effects --auth-file /protected/provider-auth.json
```

No command implicitly submits review, promotes a track, notifies external testers or releases an application. A Google binary plan explicitly declares draft append versus track-release replacement. Google listing changes apply across tracks. Image replacement binds every supplied locale/class and blocks omission of existing remote groups; deleting any existing images requires reviewed `replacement.allow_delete: true`. Supported Apple/Google slots are frozen in `catalog/store-rules-v1.json`; unsupported/new classes fail closed. Validation does not prove store submission readiness, native capture quality or device acceptance.

Execution copies reviewed inputs and the whole runtime before remote lookup, rechecks remote state, serializes the account/app target, and writes durable attempt receipts. Its registry is always `build/store-assets`; `execute` rejects another `--state` so pending/concurrent guards cannot be bypassed by changing directories. Other local snapshot commands may select `--state`. Downloaded image files and their hashes remain fully bound/staged, while remote preflight compares provider IDs/order/checksums/processing/revision rather than local `file`/`sha256` annotations. Acceptance is separate from processing/readback. Binary readback requires the actual platform as well as app/version/build. A pending or partial target blocks blind retries even under a new digest. Use the authoritative attempt receipt with its adjacent plan/staged inputs for verification. If partial effects cannot be reconciled by exact readback, keep them blocked for a separately reviewed recovery workflow; no automatic rollback or force-retry flag exists. An optional receipt copy is additional evidence, not a replacement for the attempt directory.

## Provider capabilities

The following describes code present and host tests, not validated live store functionality.

| Provider                | Download                                                                                                        | Metadata upload                                                                                                                       | Image upload                                                                             | Binary upload                                                                                                 | Build                                                              | Readback                                                                                   |
| ----------------------- | --------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------ | ------------------------------------------------------------------------------------------ |
| Apple                   | Public listing fields and all returned screenshot sets for an exact existing version; HTTPS image downloads     | Existing version/locales and exact editable app-info ID; description/keywords/promotion/notes/support/marketing/name/subtitle/privacy | Five catalog iPhone/iPad classes; explicit full locale/class replacement/deletion policy | Inspected IPA through Pilot; no submission/external distribution; localized beta notes blocked                | Generic build/inspection protocol; Mirae signed live build blocked | Exact app/platform/version/build/processing, selected text and image IDs/order/processing  |
| Google                  | Public title/short/full/video, all eight SDK image groups and selected track releases; read edit always aborted | Title/short/full/video through Supply listing; description alias canonicalized in plan                                                | Catalog phone screenshots/icon/feature graphic/TV banner only                            | Inspected AAB through Supply; explicit selected track, draft append or completed replacement, localized notes | Generic build/inspection protocol; Mirae signed live build blocked | Exact app/platform/versionCode/release name/status/notes and selected text/image IDs/order |
| Firebase / Steam / Toss | No native implementation                                                                                        | No native implementation                                                                                                              | No native implementation                                                                 | No native implementation                                                                                      | Generic protocol only; no provider distribution builder            | No native implementation                                                                   |
| Browser / OTA           | No implementation                                                                                               | No implementation                                                                                                                     | No implementation                                                                        | No implementation                                                                                             | No implementation                                                  | No implementation                                                                          |

Google download enumerates phone/seven-inch/ten-inch/TV/Wear screenshots, icon, feature graphic and TV banner. Upload validation supports only the four catalog groups; unsupported existing groups block incomplete replacement. Apple upload rules support `APP_IPHONE_65`, `APP_IPHONE_67`, `APP_IPHONE_61`, `APP_IPAD_PRO_129`, and `APP_IPAD_PRO_3GEN_129`. Native adapters are tested with synthetic SDK/transport boundaries; actual Fastlane reader, Supply image model and Supply bundle return interface are exercised locally. Live API authentication, permissions, transfers and remote processing remain unverified.

`doctor`, `plan`, `diff`, `generate`, `build`, `download`, `execute`, and `verify` are the complete new CLI command list. `plan/execute` support only binary, metadata and images. There is no capture/device automation, watch/scheduled tracking, metadata export/import workflow, history browser, native-capture attestation adapter, automatic account discovery, Firebase/Steam/Toss distribution, browser upload, OTA publishing, promotion/submission, or partial recovery command. Snapshots and manual JSON editing provide local history/diff, not those workflows. Flutter/Godot build-only argv helpers are not completed signed native builders. Other consumers remain unmigrated.

The JSON command protocol is available for reviewed application adapters. Native API authentication, actual transfer, signing, physical-device capture and store processing have not been validated by host-only tests. Public samples and fixtures contain synthetic identities.

## Checks

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
ruby -c lib/fastlane_assets.rb
ruby -c lib/store_provider.rb
```

Set `APP_STORE_ASSETS_FASTLANE_SOURCE` to unpacked Fastlane 2.240.1 and `APP_STORE_ASSETS_READER_RUBY` to an interpreter with its existing reader dependencies to test the actual screenshot reader and Supply model. These checks use temporary synthetic files and make no store calls. Legacy personal Fastfile integrations remain opt-in and are not a substitute for a migrated consumer's clean-clone tests.

## Legacy image compatibility

`assets.py prepare-screenshots` and `validate` remain local-only. `AppStoreAssets.prepare` now blocks the old approval bypass. `prepare_local` returns prepared paths without upload/replacement authorization. Consumers must migrate their store lanes to a reviewed plan rather than rely on the legacy bridge.

See the [implementation contract](docs/specs/2026-10-07-app-store-assets-design.md), [plan](docs/plans/2026-10-07-shared-runtime.md), and [implementation evidence](docs/notes/2026-10-07-implementation.md).
