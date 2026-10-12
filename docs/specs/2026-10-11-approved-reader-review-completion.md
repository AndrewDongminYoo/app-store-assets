# Approved reader review completion

The operator approved the remaining findings at 07:56 UTC on 2026-10-11.
This continues the earlier bounded history; it does not claim a clean review or reset the prior stopped rounds.

Apple field-level and selected release notes must agree for overlapping locales; equal values and non-overlapping locales remain accepted, including empty notes.
Canonical selection combines those representations without rewriting content-addressed snapshot records.
Changelog resolution uses that selection and stops at the canonical project boundary, while still validating a content-addressed content root.
Content roots outside the project reject before reading notes.
Google changelog resolution validates supplied selected notes strictly before merging; its derived copy explicitly updates the selected release notes, including an omitted notes map, without changing the caller or other releases.
This is the one necessary in-scope reader repair; the dependent PR7 integration is a normal stack-only merge.

The catalog has no macOS image contract.
Image plans reject macOS before reading or decoding listing images; text-only macOS metadata remains supported.
The decoder keeps its fresh sanitized environment even when the compatibility env argument is supplied.
The catalog stops supplying the unused argument, and the compatibility behavior is documented and tested.

Export needs an opt-in snapshot aggregate ceiling before any payload inventory hashing or decoding.
The shared inventory reader reserves regular-file sizes first and binds subsequent bounded hashes to those identities.
Repeated validation uses the same ceiling, so a later tree cannot bypass it.
The snapshot JSON retains its existing independent text ceiling.

Acceptance uses the concrete regression mechanisms, the full declared suite, Ruby syntax, scoped lint and independent adversarial review before normal push.
One initial published candidate and at most one necessary in-scope repair candidate are allowed for this continuation, with a shared hosted deadline of 10:00 UTC.
The explicitly approved findings are completed; new unrelated findings or exhausted confirmation budgets are reported separately.
No store operation, private SDK execution, force push, billing or Computer Use is authorized.
