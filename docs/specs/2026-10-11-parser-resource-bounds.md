# Parser resource bounds

The operator approved this bounded follow-up on 2026-10-11 after the first review repair exposed parser resource gaps.
It preserves the existing offline reader and transport HOLD.

Before `ZipFile` constructs a directory, the captured APK/AAB/IPA stream must declare at most 100,000 entries and at most 64 MiB of central-directory bytes.
The stdlib's bounded EOCD and ZIP64 reader locates the directory with the same prefix arithmetic as `ZipFile`.
A fixed-header streaming pass counts actual entries and validates the exact directory span and declared count.
Split volumes, malformed spans and larger directories fail before `ZipInfo` allocation.
The existing 1 GiB artifact bound, duplicate names, container-kind selection and hash binding remain in force.

PNG IHDR and JPEG SOF dimensions must be positive, at most 4096 on either axis and at most 4096 squared pixels before native decode.
This admits every dimension in the pinned catalog, whose largest axis is 3840.
Header parsing establishes a resource ceiling; full still-image decoding and catalog validation remain necessary.
ImageMagick receives explicit limits of 512 MiB memory, zero mapped cache, zero disk cache, one thread, 30 seconds, and two internal image-list entries.
The internal list requires two entries even for a single still image; final output must still describe exactly one image and match its bounded header dimensions.
The subprocess retains its 60-second outer timeout and uses an owned temporary directory.

## Completion criteria

- Oversized directory bytes, declared entries and forged low entry counts fail before `ZipFile` construction.
- Classic ZIP, ZIP64, prefixed archives and comments preserve classification.
- Huge PNG/JPEG header dimensions fail before invoking ImageMagick.
- A valid 3840 by 3840 catalog maximum PNG still decodes under the explicit limits.
- The declared full unit suite, Ruby syntax, scoped lint and independent adversarial review pass before normal push.
- Hosted CI and reviews are evaluated against the pushed SHA; old-head completion is not current evidence.

This is an approved continuation, not a reset of previous review history.
The follow-up allows one initial published candidate and one necessary in-scope repair candidate per PR, with a two-hour shared time box from 04:52 UTC.
An unrelated new domain or exhausted gate stops the loop and is reported explicitly.
Store operations, private SDK execution, force pushes and billing are excluded.
