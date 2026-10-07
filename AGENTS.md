# App Store Assets

Personal projects only.
Keep project capture and composition in their owning repositories.
This repository owns bundle preparation, shared validation, and future Asset Library transport.
Do not upload, delete placements, or submit assets for review without explicit operator authorization for the target app and operation.

## Checks

Run `python3 -m unittest discover -s tests -v`.
Run `ruby -c lib/fastlane_assets.rb` after Ruby changes.
Run `APP_STORE_ASSETS_PERSONAL_ROOT=/absolute/personal/root python3 -m unittest discover -s tests -v` for integration verification.
The integration suite is opt-in and uses personal checkouts of `mirae`, `ttush_push`, and `kkomkkomi` from that root.
It evaluates their actual Fastfiles in temporary repositories and replaces only external Fastlane actions.
Do not run real release lanes as verification.

## Contracts

Use Python's standard library and existing ImageMagick 7.
Do not add a service, database, or capture abstraction.
Preserve source images and previous bundles.
Hash final bytes after normalization or optimization.
Never promote an imported image to verified native capture without capture-time build evidence.
Write durable plans, specifications, and evidence to `docs/plans/`, `docs/specs/`, and `docs/notes/`.
