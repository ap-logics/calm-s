# Handoff validation — 24 September 2026

- Authenticated GitHub identity verified as `ap-logics` (account ID 79797252).
- All 44 harness tests passed from the assembled repository.
- All release ZIP entries scanned against the configured API key values;
  no `.env` file or matching credential was found.
- Extension archive SHA-256 verified before restoration, and every manifest
  artifact hash verified during restoration into a separate clean directory.
- 6,811 data/run files restored successfully. SQLite integrity check passed.
- Restored ledger: 3,908 completed calls, $16.0291502 cumulative cost; no pending
  calls. Remaining allowance under $99 is $82.9708498.
- No paid model API calls were made while assembling or validating this handoff.
- Coding verifier source is prepared, but Docker runtime validation remains
  pending. AppWorld and the other unfinished studies remain explicitly marked.

Archives are immutable release assets listed in `release-assets.json`; source
and handoff instructions are versioned in Git. Re-running the archive restoration
refuses to overwrite different existing data, and never resets an existing ledger.
