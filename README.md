# App Store Assets

Prepare, validate, review, and transfer App Store screenshots from your app's existing image pipeline.
The tool preserves source images, binds a reviewable plan to the exact image bytes and app version, and checks App Store Connect after a transfer.
Your app keeps ownership of capture, composition, authentication, and release lanes.

| Capability | Support |
| --- | --- |
| Prepare and validate local iOS and Android phone screenshot bundles | Python CLI; no account or network required |
| Inspect inputs and plan changes | Offline `doctor`, `plan`, and `diff` commands |
| Publish immutable local metadata and image snapshots | Python local APIs and import/export commands |
| Read and transfer App Store screenshots | Ruby bridge using an authenticated Fastlane Spaceship session; Apple iOS only |
| Capture screens, build/sign apps, upload binaries, or submit review | Outside the transfer adapter's scope |
| Transfer Google Play images, macOS screenshots, or App Previews | Not implemented |

## Requirements

Use macOS or Linux with Git, Python 3.9 or newer, and ImageMagick 7 (`magick`) on `PATH`.
The Python code uses the standard library; there is no `pip install` step.
Remote reads and transfers additionally require Ruby and Fastlane in your app's environment.
The transfer implementation was checked against Fastlane 2.240.1 and 2.241.0; other versions need compatibility verification.
Use your app's `Gemfile.lock` to keep its tested Fastlane version stable.

```bash
python3 --version
magick -version
ruby --version
bundle exec fastlane --version
```

The walkthrough below uses an app with `fastlane/Fastfile` at its root and an existing Fastlane installation.
For another layout, adjust the `APP_ROOT` calculation in the Ruby example and its path in the preparation script.
All example app identifiers, versions, images, and account labels must be replaced with your own.

## Install a version

Install the `v1.1.0` source checkout inside your app.
Use a real directory, not a symlink or a downloaded source archive: the current runtime verifier reads Git identity as well as file contents.
This is a source distribution, not a Python package or Fastlane plugin.

```bash
export APP_ROOT="/absolute/path/to/your-app"
export APP_ROOT="$(cd "$APP_ROOT" && pwd -P)"
export APP_STORE_ASSETS_ROOT="$APP_ROOT/tools/app-store-assets"
export PYTHONDONTWRITEBYTECODE=1
export PYTHON="$(command -v python3)"
mkdir -p "$APP_ROOT/tools" "$APP_ROOT/scripts" "$APP_ROOT/fastlane" "$APP_ROOT/store-assets"
git clone --branch v1.1.0 --depth 1 \
  https://github.com/AndrewDongminYoo/app-store-assets.git \
  "$APP_STORE_ASSETS_ROOT"
```

Keep this nested checkout out of the app's tracked files, for example with `/tools/app-store-assets/` in the app's `.gitignore`.
Keep generated bundles in `/build/` as well.
Do not place app configuration, images, or credentials inside the runtime checkout: it must stay clean.
The preparation example below records the resolved version and runtime file hashes automatically in `store-upload.json`.
You do not need to copy a commit SHA from this README.

A release tag selects a version; the recorded source identity and hashes detect a changed installation.
Reproducibility also depends on your source images, ImageMagick version, Python/Ruby environment, and Fastlane lockfile.
Record those tool versions in your CI environment or build image rather than assuming a Git revision describes the entire pipeline.

## Integrate an iOS screenshot pipeline

The sequence is **prepare local images → read store state → plan → approve → verify live state → transfer**.
Only the final step writes to App Store Connect.
An offline plan is always non-executable; a separate approval binds it to one app/version and operation.

### 1. Describe the target and image order

Create `store-assets/target.json` in your app:

```json
{
  "store": "apple",
  "platform": "ios",
  "account": "app-store-team",
  "app_id": "com.example.myapp",
  "flavor": "production",
  "stage": "production",
  "version": { "name": "1.0.0", "build": "1" }
}
```

`app_id` is the bundle identifier, not Apple's numeric app ID.
`account` is your public account label; it does not authenticate or verify a team.
An optional public `account_id` must then appear unchanged in every target record, including the approval.
Set `version` to the App Store version and attached build you intend to edit.
The version must be editable, have no active review, and already have the required localizations and build selected.
This tool does not create the version, attach a build, or create localizations.

Create `store-assets/selection.json`:

```json
{
  "remote": "store-assets/remote.json",
  "allow_delete": false,
  "images": {
    "en-US": {
      "APP_IPHONE_67": [
        "store-assets/source/en-US/01.png",
        "store-assets/source/en-US/02.png"
      ]
    }
  }
}
```

Put your final composed screenshots at those paths.
Array order is the intended store order; add other locales or slots explicitly.
For this example, use opaque PNG or JPEG images at a supported `APP_IPHONE_67` size, such as 1290 × 2796 pixels.
Use lowercase `.png`, `.jpg`, or `.jpeg` extensions that match the encoded format.
The [supported slot catalog](catalog/store-rules-v1.json) lists the sizes and limits this version validates; it is not a complete device catalog or a guarantee of store acceptance.

Start with `allow_delete: false`: an absent or empty screenshot set can be populated, and an identical set can be kept.
A different non-empty set is refused.
To replace an existing set, explicitly change this to `true` before preparing and reviewing a new plan.
That permits deleting screenshots within the declared locale/slot pairs, not unrelated sets.
Review visual quality and localization separately; byte validation cannot do that.

### 2. Prepare immutable image inputs

Save the following app-owned helper as `scripts/prepare-store-assets.py`.
It uses the existing local snapshot API because the standalone bundle command does not create the live planner's asset manifest and profile.
It captures final bytes, publishes an immutable snapshot, and writes the listing and profile used in the remaining steps.

```python
import hashlib
import json
import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
runtime = root / "tools/app-store-assets"
sys.path.insert(0, str(runtime))

from app_store_assets.contracts import target_identity
from app_store_assets.identity import runtime_identity, runtime_inventory
from app_store_assets.records import capture_bytes, read_json, safe_path
from app_store_assets_local.publisher import publish_snapshot


def write_json(name, value):
    destination = root / name
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def git(*args):
    return subprocess.check_output(
        ["git", "-C", str(runtime), *args], text=True
    ).strip()


target = target_identity(read_json(safe_path(root, "store-assets/target.json")))
selection = read_json(safe_path(root, "store-assets/selection.json"))
pin = {
    "path": "tools/app-store-assets",
    "url": git("remote", "get-url", "origin"),
    "commit": git("rev-parse", "HEAD"),
    "files": runtime_inventory(runtime),
}
runtime_identity(runtime, pin)
entries, files = [], {}
for locale, groups in selection["images"].items():
    for slot, sources in groups.items():
        for index, source in enumerate(sources, 1):
            original = safe_path(root, source)
            data = capture_bytes(original, limit=64 * 1024 * 1024)
            name = f"{locale}/{slot}/{index:02d}{original.suffix}"
            files[name] = data
            entries.append({
                "file": name, "locale": locale, "slot": slot,
                "sha256": hashlib.sha256(data).hexdigest(),
            })
record = {
    "schema_version": 1, "type": "asset-manifest", "target": target,
    "assets": entries, "provenance": {"status": "unverified-import"},
}
snapshot = publish_snapshot(root / "build/store-assets/assets", record, files)
images = {}
for entry in entries:
    images.setdefault(entry["locale"], {}).setdefault(entry["slot"], []).append({
        "file": (snapshot / entry["file"]).relative_to(root).as_posix(),
        "sha256": entry["sha256"],
    })
write_json("store-assets/listing.json", {
    "schema_version": 1, "type": "metadata", "target": target, "images": images,
})
write_json("store-upload.json", {
    "schema_version": 1, "type": "offline-profile", "project": "my-app",
    "mode": "live", "runtime": pin,
    "targets": {"ios-production": {
        **target,
        "inputs": ["store-assets/target.json", "store-assets/selection.json",
                   "scripts/prepare-store-assets.py", "fastlane/Fastfile"],
        "metadata": "store-assets/listing.json",
        "assets": {"manifest": (snapshot / "manifest.json").relative_to(root).as_posix()},
        "remote": selection["remote"],
        "replacement": {
            "locales": list(images),
            "slots": sorted({entry["slot"] for entry in entries}),
            "allow_delete": selection["allow_delete"],
        },
    }},
})
print(snapshot)
```

Run it after your capture/composition step:

```bash
python3 -B "$APP_ROOT/scripts/prepare-store-assets.py"
```

This helper replaces `store-assets/listing.json` and `store-upload.json` when rerun; it preserves original images and prior content-addressed snapshots.
Keep the generated profile and all referenced snapshot bytes together for review and execution.
The provenance remains `unverified-import`: selecting a build number does not prove that build rendered the screenshots.

### 3. Connect the Ruby bridge to Fastlane

Add these lanes to your app's `fastlane/Fastfile`, adjusting names to avoid conflicts.
The example uses a team API key supplied outside the repository through your local environment or CI secret manager.
`ASC_KEY_ID`, `ASC_ISSUER_ID`, and `ASC_KEY_FILE` are environment names used by this example, not fields in a public profile.
`ASC_KEY_FILE` must point to the private `.p8` file outside the app and runtime directories.
Fastlane's [API key action](https://docs.fastlane.tools/actions/app_store_connect_api_key/) sets the Spaceship token; an existing authenticated Apple ID session can be used instead.
Configure and verify the intended App Store Connect account in your own lane.

```ruby
require "json"

APP_ROOT = File.realpath(File.join(__dir__, ".."))
require File.join(APP_ROOT, "tools/app-store-assets/lib/fastlane_assets.rb")

def store_assets_target
  JSON.parse(File.read(File.join(APP_ROOT, "store-assets/target.json")))
end

platform :ios do
  private_lane :store_assets_auth do
    app_store_connect_api_key(
      key_id: ENV.fetch("ASC_KEY_ID"),
      issuer_id: ENV.fetch("ASC_ISSUER_ID"),
      key_filepath: ENV.fetch("ASC_KEY_FILE"),
      set_spaceship_token: true
    )
  end

  lane :store_assets_snapshot do |options|
    store_assets_auth
    AppStoreAssets.export_snapshot(
      target: store_assets_target,
      output: File.join(APP_ROOT, options.fetch(:output, "store-assets/remote.json"))
    )
  end

  lane :store_assets_verify do |options|
    store_assets_auth
    AppStoreAssets.transfer_screenshots(
      root: APP_ROOT, target: store_assets_target,
      plan: options.fetch(:plan, "store-assets/plan.json"),
      approval: options.fetch(:approval, "store-assets/approval.json"),
      mode: "read-only"
    )
  end

  lane :store_assets_transfer do |options|
    store_assets_auth
    AppStoreAssets.transfer_screenshots(
      root: APP_ROOT, target: store_assets_target,
      plan: options.fetch(:plan, "store-assets/plan.json"),
      approval: options.fetch(:approval, "store-assets/approval.json"),
      mode: "transfer"
    )
  end
end
```

Do not call the legacy `AppStoreAssets.prepare`; it intentionally raises an error.
Do not pass prepared paths to an unrestricted `deliver` screenshot replacement alongside these lanes.
Other binary or metadata lanes should skip screenshot upload so there is one controlled screenshot writer.
The bridge cannot intercept independent Fastlane calls or App Store Connect web edits.

### 4. Export current store state and create a plan

With authentication configured, export a snapshot.
This reads App Store Connect and creates a new local file; it makes no remote write and refuses to overwrite an existing output.

```bash
(cd "$APP_ROOT" && bundle exec fastlane ios store_assets_snapshot)
```

Then run the offline checks from the runtime checkout:

```bash
cd "$APP_STORE_ASSETS_ROOT"
python3 -B -m app_store_assets doctor \
  --root "$APP_ROOT" --target ios-production
(
  set -o noclobber
  python3 -B -m app_store_assets plan \
    --root "$APP_ROOT" --target ios-production --operation images \
    > "$APP_ROOT/store-assets/plan.json"
)
```

Stop if any command exits non-zero.
The plan command refuses to overwrite an existing file; use a new filename for another attempt, including after a failed command leaves an empty output.
`doctor` checks the runtime and bound local assets; it does not authenticate or verify remote freshness.
`plan` validates the supplied store snapshot and emits `{"payload": ..., "digest": ...}`.
It still reports `executable: false`, `effects: []`, and `remote_verified: false`.
Only the subsequent Ruby live check compares that observation with App Store Connect.

Profile paths and input paths are relative to the app root.
Keep inputs explicit: do not list the whole `store-assets` directory in `inputs`, because a later plan or approval file there would change its own input inventory.
Do not change the profile, Fastfile, helper, selected images, or other bound inputs between planning and transfer.

### 5. Review and approve the exact plan

Review the target, version/build, ordered image paths and hashes, locales/slots, supplied remote state, and deletion policy in `store-assets/plan.json`.
The plan contains no visual preview.
Open each file named by `payload.listing.images` in an image viewer, resolving its `file` path relative to the app root, and check the screenshots in array order.
These are the immutable snapshot images that will be transferred; check their content and localization, and confirm which remote sets must remain untouched.
An operator must authorize the target and upload operation, plus deletion if `allow_delete` is true.
After that review, create `store-assets/approval.json` by copying the plan's `digest` and complete `payload.target` into this structure:

```json
{
  "schema_version": 1,
  "type": "transfer-approval",
  "plan_digest": "COPY_THE_PLAN_DIGEST",
  "target": {
    "store": "apple",
    "platform": "ios",
    "account": "app-store-team",
    "app_id": "com.example.myapp",
    "flavor": "production",
    "stage": "production",
    "version": { "name": "1.0.0", "build": "1" }
  },
  "operation": "images"
}
```

The digest must be the actual 64-character value; the placeholder is intentionally invalid.
Copy any `account_id` from the plan too.
The approval is separate from the plan and its inputs.
Do not automatically approve a freshly generated plan in CI: the JSON binds a decision but does not prove who made it.

### 6. Verify live state, then transfer

First run the read-only lane with the reviewed files:

```bash
(cd "$APP_ROOT" && bundle exec fastlane ios store_assets_verify)
```

A successful read-only result means the supplied observation matches live state and the expected build is attached.
It does not upload images or certify their processing completion.
Before transfer, establish an exclusive writer window: no other machine, lane, or App Store Connect user may change screenshots, the selected build, or the version/review state until final verification finishes.
The local lock only prevents concurrent runs on the same machine.

Run the following only after the operator has authorized the reviewed transfer:

```bash
(cd "$APP_ROOT" && bundle exec fastlane ios store_assets_transfer)
```

The adapter re-verifies the plan and approval, stages hash-checked bytes, and compares the remote state before writing.
It populates absent/empty groups, keeps identical groups, and replaces different non-empty groups only with deletion authorized.
It preserves other screenshot sets in declared locales and does not write undeclared locales.
Success requires the planned screenshot count, ordered MD5 checksums, completed processing, unchanged preserved sets, and the expected build and editable version in the final read.
MD5 is the provider's comparison value; SHA-256 binds the local approved bytes.

The bridge returns a Ruby result hash and emits one JSON result; provider output goes to standard error.
Fastlane itself adds its own console output, so a complete `bundle exec fastlane` log is not a JSON document.
Retain the plan, approval, local snapshots, remote observation, and result as release evidence in your app's pipeline.
The tool never submits the app for review.

### 7. Retry, upgrade, and run in CI

A transfer failure can leave remote changes in place; there is no automatic rollback.
Check the reported possibly changed groups before proceeding.
For a retry, preserve the previous records, choose a new `remote` filename in `selection.json`, prepare again, and export to that path with `store_assets_snapshot output:store-assets/remote-next.json`.
Create a new plan and approval, then pass their relative paths using the lanes' `plan:` and `approval:` options.
Do not reuse an old approval after remote state or a bound input changes.

In CI, separate preparation/review from the explicitly approved transfer job.
Restore the exact runtime and image snapshots named by the profile, use the same locked toolchain, and inject credentials only into jobs that need store access.
Use a protected manual approval step and serialize writers across machines.
A plan is not a deployment credential or a substitute for that approval.

To restore the recorded runtime on another machine, clone it to the same app-relative path and check out its recorded identity:

```bash
export APP_ROOT="/absolute/path/to/your-app"
export APP_STORE_ASSETS_ROOT="$APP_ROOT/tools/app-store-assets"
export PYTHONDONTWRITEBYTECODE=1
export PYTHON="$(command -v python3)"
runtime_revision="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["runtime"]["commit"])' "$APP_ROOT/store-upload.json")"
git clone https://github.com/AndrewDongminYoo/app-store-assets.git "$APP_STORE_ASSETS_ROOT"
git -C "$APP_STORE_ASSETS_ROOT" checkout --detach "$runtime_revision"
```

To upgrade intentionally, check out a new reviewed release tag, rerun preparation and verification, and review the changed profile and toolchain locks.
Regenerate plans and approvals after the upgrade.
Do not run `git pull` inside the runtime as part of an approved transfer job.

## Local bundles without store integration

If you only need validated images for another tool, use the standalone CLI.
It expects locale directories under `--source`; `--subdir` selects an optional directory below each locale.
For example, `source/en-US/01.png` uses `--subdir .`, while `source/en-US/images/iphone67/01.png` uses `--subdir images/iphone67`.

```bash
python3 "$APP_STORE_ASSETS_ROOT/assets.py" prepare-screenshots \
  --source "$APP_ROOT/store-assets/source" --subdir . \
  --out "$APP_ROOT/build/store-assets/bundles" \
  --project my-app --bundle-id com.example.myapp
python3 "$APP_STORE_ASSETS_ROOT/assets.py" validate /absolute/path/to/returned/bundle
```

Preparation prints JSON with `bundle` and `screenshots_path`.
The bundle manifest records original and final hashes, sizes, profiles, and inventory; `validate` decodes the images and checks those final bytes.
Original inputs and earlier bundles remain intact.
`--normalize-alpha` removes an unused alpha channel from an otherwise opaque PNG copy; actual transparent pixels require a background in your image composer.
Output bytes are deterministic for identical input bytes within the same ImageMagick runtime.
A bundle is not the immutable asset snapshot used by the live planner and does not authorize upload.

### Android phone screenshots

Use `--platform android` to validate phone screenshots against the existing Google slot catalog.
Omitting the option, or selecting `--platform ios`, preserves the existing iPhone/iPad behavior and bundle format.
Android local bundles are available from `v1.1.0`; the earlier `v1.0.0` release supports only iOS local bundles.

```bash
python3 "$APP_STORE_ASSETS_ROOT/assets.py" prepare-screenshots \
  --platform android \
  --source "$APP_ROOT/fastlane/metadata/android" --subdir images/phoneScreenshots \
  --out "$APP_ROOT/build/store-assets/android-bundles" \
  --project my-app --bundle-id com.example.myapp
python3 "$APP_STORE_ASSETS_ROOT/assets.py" validate /absolute/path/to/returned/android-bundle
```

For Android, `--bundle-id` carries the app's Android package name.
Each locale may contain up to eight JPEG or 24-bit RGB PNG phone screenshots, with no alpha channel.
Each dimension must be between 320 and 3840 pixels, and the longest edge cannot exceed twice the shortest.
The validator accepts portrait and landscape images and excludes sibling icons and feature graphics through the selected subdirectory.
It checks local file rules; it does not establish the store's publication minimum across device types, promotional eligibility or listing completeness.
See the [Google Play preview asset requirements](https://support.google.com/googleplay/android-developer/answer/9866151?hl=en).

Android manifests use `schema_version: 2`, `platform: android` and profile `phoneScreenshots`; validation reads the platform from the manifest.
Existing iOS manifests stay at version 1, including their original bundle identities.
Earlier validators reject the Android schema rather than treating it as an iOS bundle.
The Ruby `prepare_local` helper and live transfer bridge remain iOS-only; Android support adds no Google Play reads or writes.

Ruby callers can use `AppStoreAssets.prepare_local(repo_root:, project:, bundle_id:, source:, subdir: ".", normalize_alpha: false)`.
It returns `screenshots_path` without `overwrite_screenshots`.

## Troubleshooting

| Refusal or symptom | What to check |
| --- | --- |
| Runtime commit, URL, inventory, or executing runtime differs | Restore the checkout recorded in the profile; invoke Python from that runtime, keep it clean, and use `-B` or `PYTHONDONTWRITEBYTECODE=1`. Existing caches from another Python version still cause refusal; use a fresh checkout without those caches. |
| Image format, dimensions, alpha, or slot rejected | Check decoded bytes against the catalog; fix the owning composer or select the correct slot. |
| Apple version locale unavailable | Create that localization on the selected version, then export a fresh snapshot and plan again. |
| Version/build differs, active review, or version not editable | Select the intended build and an editable version before taking a new snapshot. |
| Snapshot output already exists | Choose a new output filename and update the selection's `remote` path; preserve the old observation. |
| Plan, approval, or live snapshot differs | Rebuild the plan from current inputs and obtain a new approval; do not edit a digest to bypass verification. |
| A non-empty group differs and deletion is not allowed | Review whether replacement is intended; enable deletion only in a newly reviewed plan. |
| Target lock exists | Check whether a run is still active; only an operator should remove a confirmed stale lock. |
| Provider timeout or partially changed groups | Inspect the result, take a new snapshot, and replan; do not assume a timeout means no write occurred. |

Provider and local-verifier calls default to 120 seconds each.
Transfer groups default to a 600-second deadline with 5-second polling and a 60-second request timeout.
The Ruby entrypoint accepts `deadline`, `verification_deadline`, `group_deadline`, `poll_interval`, and `request_timeout`, each positive and at most 600 seconds.
The bundle-ID lock lives at `/tmp/app-store-assets-transfer-<SHA-256 of bundle ID>.lock`.
Staging is private and cleaned by the adapter; detected replacements are retained at the reported path for recovery.

## Development and reference

Run the default checks from this repository:

```bash
python3 -m unittest discover -s tests -v
ruby -c lib/fastlane_assets.rb
ruby -c lib/fastlane_transfer.rb
```

The default suite uses temporary fixtures and fake store providers, with no live upload or credentials.
Consumer-specific and Fastlane-reader integration checks are opt-in; a skipped check is not live store verification.
Their setup is in [the integration tests](tests/test_fastlane.py) and [reader tests](tests/test_fastlane_reader.py).

The offline CLI also supports `plan --operation metadata`, `plan --operation binary`, and `diff --before PATH --after PATH`; these remain read-only and do not implement those transfers.
`python3 -B -m app_store_assets_local --help` describes local metadata import/export; it makes no store call.
Use `--help` on each CLI for available arguments.

- [Offline profile schema](schemas/offline-profile-v1.json) and [record schemas](schemas/records-v1.json).
- [Transfer approval schema](schemas/transfer-approval-v1.json) and [transfer invariants](docs/specs/2026-10-14-guarded-screenshot-transfer.md).
- [Local bundle contract](docs/specs/screenshot-bundles.md).

Python validators are authoritative; JSON schemas summarize structure.
Historical implementation plans and app-specific evidence remain under `docs/plans/` and `docs/notes/`; they are not installation instructions.

## License

[MIT](LICENSE), copyright Dongmin Yu.
ImageMagick, Fastlane, Python, and Ruby are separately installed tools and retain their own licenses.
See [ImageMagick's license](https://imagemagick.org/license/), [Fastlane's MIT license](https://github.com/fastlane/fastlane/blob/master/LICENSE), [Python's license](https://docs.python.org/3/license.html), and [Ruby's license](https://www.ruby-lang.org/en/about/license.txt).
