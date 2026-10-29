# App Store Assets

Personal projects only.
Keep project capture and composition in their owning repositories.
This repository owns bundle preparation, shared validation, and future Asset Library transport.
Do not upload, delete placements, or submit assets for review without explicit operator authorization for the target app and operation.

## Checks

Run `env -u APP_STORE_ASSETS_PERSONAL_ROOT -u APP_STORE_ASSETS_FASTLANE_SOURCE python3 -m unittest discover -s tests -v` for offline verification.
Select Python 3.14 and Ruby 3.4 for these local checks; the README records the observed Python 3.15.1 and Ruby 4.0.9 compatibility limits.
Run `ruby -c` on both `lib/fastlane_assets.rb` and `lib/fastlane_transfer.rb`, plus changed Ruby harnesses.
Run `trunk check --no-fix` for changed files and `trunk check --all --no-fix --jobs=2` for a full baseline.
Trunk checks workflows, action pins, Git diff whitespace, and candidate secrets without verifying them against external accounts.
The local TruffleHog filesystem reader retains decoded findings at file level when their raw value has no literal source location, and fails invalid JSONL conversion.
Run `python3 -m unittest discover -s .trunk/configs/tests -v` for its command-line regression tests; CI runs these separately from the CLI suite.
Keep automatic formatting disabled until a scoped preview is accepted.
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
