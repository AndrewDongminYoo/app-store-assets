# Quality Tooling Refresh Plan

## Work and Verification

1. Inspect repository instructions, workflow, runtime requirements, and supplied Oracle precedent → verify with direct file reads and Git identity.
2. Add only the supported Trunk baseline and documented local-state ignores → verify with `trunk config print` and `trunk actions list`.
3. Prove offline secret detection and suppress only the synthetic URI fixture rule → verify the initial failing scan, unchanged fixture bytes, and the subsequent clean scan.
4. Run offline regression and syntax checks → verify with the commands below and captured exit statuses.
5. Reconcile gate claims and review the scoped diff → verify with the full no-fix scan and `git diff --check`.
6. Return evidence to the root agent for local review, commits, and publication approval.

## Declared Gates

```bash
magick -version
env -u APP_STORE_ASSETS_PERSONAL_ROOT -u APP_STORE_ASSETS_FASTLANE_SOURCE PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
ruby -c lib/fastlane_assets.rb
ruby -c lib/fastlane_transfer.rb
ruby -c tests/fastlane_harness.rb
ruby -c tests/snapshot_export_harness.rb
ruby -c tests/transfer_readback_harness.rb
ruby -c tests/fake_spaceship/spaceship.rb
ruby -c tests/fake_spaceship/transfer.rb
trunk check --all --no-fix --jobs=2
```

## Evidence and Boundaries

Store command evidence outside this checkout at `/Volumes/dongminyu/Development/01_personal/pr-loop-reviews/app-store-assets/2026-10-28-quality-refresh`.
Do not run real Fastlane, authentication, consumer integration, screenshot regeneration, or store operations.
A skipped optional integration check remains unverified.
Automatic pre-commit formatting remains disabled.
