# App Store Assets

Shared image-bundle preparation for personal App Store projects.
Existing project capture and artwork generators remain the source of images.
The first adoption covers Mirae, Ttush Push, and Kkomkkomi Fastlane uploads, plus the App Store copyright fix in Chef al Mando's composer.

## Requirements

Python 3.9 or newer, ImageMagick 7 (`magick`), and Ruby for the Fastlane bridge.
No new Python package or Ruby gem is required.
Keep this checkout beside the personal app repositories or set `APP_STORE_ASSETS_ROOT` to its absolute path.
The [shared repository](https://github.com/AndrewDongminYoo/app-store-assets) is private.
Use a reviewed runtime commit for reproducible installation.
Missing tooling stops screenshot uploads with an explicit error.

## Runtime Checkout

The stage-1 runtime pin `e0d3691b455ec2c27606fbda5b22f09f5a9d3483`, also included in `d9682e6`, has reader-compatibility and cache-publication defects.
Do not use those revisions for store uploads.
The replacement runtime candidate is `7597d47f3ce36cac3462155b0c8a489a441e62a8`.
Review and merge its fix PR before deploying this pin.
After approval, clone into a new directory and set its absolute path for the app's Fastlane bridge.

```bash
git clone --no-checkout https://github.com/AndrewDongminYoo/app-store-assets.git /absolute/path/to/app-store-assets
git -C /absolute/path/to/app-store-assets checkout --detach 7597d47f3ce36cac3462155b0c8a489a441e62a8
export APP_STORE_ASSETS_ROOT=/absolute/path/to/app-store-assets
```

Project lane adoption remains in each owning app repository; those app changes are not included in this repository's publication.

## Prepare without uploading

```bash
python3 assets.py prepare-screenshots \
  --source ../mirae/fastlane/metadata/ios \
  --subdir images/iphone65 \
  --out ../mirae/build/store-assets/ios-bundles \
  --project mirae --bundle-id kr.mirae.app
```

The command returns JSON containing `bundle` and `screenshots_path`.
Each locale is flattened to the direct image layout Fastlane reads.
The bundle directory is named from the manifest hash and contains final hashes, original hashes, sizes, profiles, and the explicit `replace-localized-sets` policy.
`validate` re-decodes images and compares final hashes and inventory.
Preparation additionally compares a reused bundle's manifest with the manifest freshly computed from the source.
Concurrent preparations validate and reuse the atomically published winner.

```bash
python3 assets.py validate /absolute/path/to/bundle
python3 -m unittest discover -s tests -v
ruby -c lib/fastlane_assets.rb
```

The default suite runs the standalone CLI tests and explicitly skips consumer integration tests.
GitHub Actions runs this default suite and Ruby syntax checks on pull requests targeting `main` and pushes to `main`.
The single Ubuntu 24.04 job installs ImageMagick 7 through the runner's existing Homebrew and uses Python 3.12 with read-only repository permissions.
Consumer integration and the optional Fastlane reader checks remain local because they require additional checkouts or reader dependencies.
To verify actual adopted Fastfiles, set `APP_STORE_ASSETS_PERSONAL_ROOT` to the folder containing the personal `mirae`, `ttush_push`, and `kkomkkomi` checkouts with the stage-1 lane changes.

```bash
APP_STORE_ASSETS_PERSONAL_ROOT=/absolute/personal/root python3 -m unittest discover -s tests -v
```

To compare the manifest with the actual Fastlane 2.240.1 loader, point to its unpacked source and a Ruby interpreter with its existing reader dependencies.
This check reads temporary files and makes no store calls.

```bash
APP_STORE_ASSETS_FASTLANE_SOURCE=/absolute/path/to/fastlane-2.240.1 \
APP_STORE_ASSETS_READER_RUBY=/absolute/path/to/ruby \
python3 -m unittest discover -s tests -v
```

`--normalize-alpha` removes an unused alpha channel from an entirely opaque PNG in the prepared copy.
It rejects actual transparent pixels, which require an explicit background in the owning composer.
Original inputs remain unchanged.
PNG encoding excludes date and time chunks while retaining color metadata, so identical input bytes produce identical output within the same ImageMagick runtime.
Ttush's Fastlane bridge enables this option for its existing iPad inputs.

## Upload behavior

The adopted Fastlane lanes prepare and validate images before account lookup or upload, then pass the exact prepared path and `overwrite_screenshots: true`.
Hidden screenshot filenames, mixed-case extensions such as `.Png`, and mismatched file formats are rejected before the external boundary.
Replacement affects **all screenshot sets in every supplied locale**, as implemented by Fastlane, including remote display classes absent from the local tree.
Review the complete local and remote sets before executing the lane.
Mirae and Ttush retain their in-progress-review guard.
Their release lanes also validate before starting the build.
`skip_screenshots:true` explicitly permits metadata-only upload without this checkout.
Kkomkkomi retains its metadata-only fallback when its screenshot source directory is absent.

No command in this repository currently logs into App Store Connect, uploads files, or submits review.
Fastlane lane execution remains an external action requiring authorization.
`overwrite_screenshots` expresses replacement intent; it does not prove remote processing, order, or absence of duplicates.
Remote readback belongs to the later Asset Library adapter.

## Evidence limits

The initial manifest labels existing inputs `unverified-import`.
It records file provenance, not the build that originally rendered the image.
It does not assert required-slot completeness, text readability, visual quality, safe-area compliance, or App Store acceptance.
The current dimension allowlist covers the adopted iPhone and iPad pipelines; it is not a complete Apple device catalog.
Duo and Creative Assets require the next reference-data and provenance contract rather than aliases for existing phone screenshots.

See [the rollout](docs/plans/2026-10-07-rollout.md) and [the first-stage contract](docs/specs/screenshot-bundles.md).
