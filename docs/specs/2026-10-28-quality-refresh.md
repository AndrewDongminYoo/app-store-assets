# Quality Tooling Refresh

## Approved Scope

Add a minimal local quality gate for this standard-library Python and Ruby bridge repository.
Keep ImageMagick 7 and the consumer-owned Fastlane lockfile as existing runtime requirements.
Preserve product APIs, screenshot bytes, consumer pins, and store-operation boundaries.

## Baseline

Pin Trunk CLI `1.25.0`, its official plugin `v1.11.0`, and the managed Python runtime `3.14.4`.
Enable `actionlint@1.7.12` for the existing GitHub Actions workflow, `pinact@4.1.1!` with `lint` and `upgrade`, `git-diff-check`, and `trufflehog@3.99.7`.
TruffleHog scans candidate secrets with `--no-verification --no-update`; it does not authenticate with providers or validate credentials.
Use the local filesystem JSONL reader through `direct_configs` and the parser override while retaining inherited SARIF output, success codes `0` and `183`, and the `copy_targets` sandbox.
The reader retains file-level findings when decoded raw values have no literal source location and fails invalid conversion without emitting clean SARIF.
Its messages omit raw and redacted credential values.
A single `trufflehog/URI` suppression on the synthetic `example.com` credential fixture preserves its validator regression test.
Do not add dependency manifests, style formatters, image optimizers, or broad ignores.
Enable the non-mutating pre-push check and keep automatic pre-commit formatting disabled pending an accepted scoped preview.
The current CI remains responsible for its existing tests and Ruby syntax checks and runs the reader's Python command-line tests separately; this change does not add a hosted Trunk job.

## Acceptance

- `magick -version` reports ImageMagick 7.
- The default Python suite passes with both optional integration environment variables unset.
- `ruby -c` passes for both library bridges and the CI and provider harnesses.
- `trunk check --all --no-fix --jobs=2` passes with the configured tools.
- The resolved configuration retains both Pinact commands and the offline secret scanner command.
- A failing scan on the synthetic URI fixture proves that the scanner executes before its exact-rule suppression is accepted.
- `python3 -m unittest discover -s .trunk/configs/tests -v` passes all 13 reader boundary tests.
- Encoded and literal synthetic credential controls fail the configured offline gate, while a clean control passes.
- Directly affected README and AGENTS gate claims match the implemented configuration and existing CI.

## Limits and Publication

These checks do not verify consumer checkouts, real Fastlane readers, store accounts, screenshots, transfers, or releases.
No project dependency manifest or lockfile requires regeneration.
The default local Python 3.15.1 and Ruby 4.0.9 run exposes a bytecode-cache comparison failure and a fake-provider `logger` loading failure under `--disable-gems`.
The affected targeted controls pass with installed Python 3.14.9 and Ruby 3.4.1.
Use an evidence-local Ruby PATH shim and an explicit Python interpreter for the full offline gate; do not change product identity validation or consumer dependencies to correct the local runner.
Push and PR creation require explicit repository-specific approval.

## Precedent

The supplied Oracle retrieval at source commit `9670d54de3076c5239713f54900c7a855bd18478` has unverified freshness.
`wiki/concepts/trunk-quality-gate-agent.md` and `wiki/concepts/authoring-time-vs-runtime-verification.md` confirm the chosen direction of preserving repository boundaries and distinguishing static checks from integration proof.

## Source-Line Repair

The current reader uses the independently reviewed `localizations` repair at `b47e59659a886ad673a2f4a9bed6a3bf4986615b`.
It prefers a positive integer filesystem line only when the literal starts on that line.
Invalid hints retain literal-search and file-level fallbacks.
Thirteen CLI tests cover repeated and out-of-order findings in addition to the existing lossless conversion cases.
