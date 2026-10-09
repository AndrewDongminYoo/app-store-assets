# B extraction plan

1. Freeze the separate offline profile/plan contract and safe negative cases.
   Reproduce the five assigned defects on preserved PR3 in a temporary copy,
   using only planner/validator calls and synthetic records. Do not reuse scripts
   that overwrite historical evidence or reach execution/generation adapters.
2. Add regression tests first; observe baseline RED. Extract records, identity,
   environment, snapshots, catalog and pure metadata/import/export. Remove
   download entirely. Replace the profile/planner/CLI effect dependency graphs
   with offline-only code; extract `stage_inventory` to a local staging module.
3. Validate state, URL/name, retained image hashes, typed binary containers,
   changed input/runtime pins, snapshot mutation/concurrency, metadata roundtrip,
   no effect imports and zero-write dry-run. Run the unchanged A/base gates.
4. Perform one independent read-only review against this spec; fix verified
   in-scope defects and repeat affected/full gates. Maximum two review cycles;
   stop for a finer split on nonconvergence or a dependency requiring C/D/E.
5. Record passing, failing and unexecuted gates separately. Create normal local
   commits and a concrete PR draft. Preserve/export candidate bytes, verify
   historical state/proofs and held Mirae pin, then safely remove the owned
   worktree. No remote B action is authorized by A publication authority.
