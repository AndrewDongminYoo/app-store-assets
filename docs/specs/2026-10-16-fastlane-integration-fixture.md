# Fastlane Integration Fixture

This correction implements [issue #41](https://github.com/AndrewDongminYoo/app-store-assets/issues/41).
The opt-in integration tests must run each consumer's actual Fastfile and its required local helper code in the temporary checkout.

## Problem

Mirae's Fastfile requires `scripts/store_assets/fastlane.rb`, but the fixture copies only the Fastfile.
Ruby exits before producing the harness report, and Python's JSON decoding error hides the original loading failure.
The current Mirae helper also requires `plan` and `expected_digest` for metadata operations, including calls with `skip_screenshots: true`.
The issue's older metadata-only success expectation conflicts with that consumer contract.

## Contract

- Copy Mirae's actual required helper to its original relative path without changing its behavior.
- Keep the Ruby harness's existing external-action stubs and process/network prohibitions.
- Preserve screenshot rejection checks for Mirae, Ttush Push, and Kkomkkomi.
- Require Mirae metadata-only calls without the reviewed plan and digest to fail before upload or review lookup.
- Preserve metadata-only success assertions for the legacy Ttush Push and Kkomkkomi lanes.
- When the subprocess emits no valid JSON report, fail with the project, exit code, stdout, and stderr rather than an unexplained JSON decoding exception.
- Keep actual personal checkout integration opt-in and the default suite independent of those checkouts.

## Scope

Change the Python test fixture and its regression coverage.
Do not change consumer repositories, Ruby business logic, runtime behavior, dependencies, or release lanes.
No real store operation is part of verification.

## Acceptance

1. A default-suite synthetic Fastfile can load a copied local helper and return the helper's rejection through the real Ruby harness.
2. Empty and malformed JSON output produce diagnostics that retain the original Ruby output and exit status.
3. The opt-in tests reach the actual Mirae plan/digest rejection, including metadata-only calls, while retaining the other consumers' expectations.
4. The default and opt-in full suites pass using the declared test commands.
