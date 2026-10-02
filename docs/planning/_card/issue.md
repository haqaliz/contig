# Card: signature-stable canonical payload

Source: inline brief (no GitHub issue; from /contig-next handoff, 2026-10-02).

## Brief

Signed Contig bundles (RunRecord and ReproduceRecord, Ed25519 via `src/contig/signing.py`) stop
verifying whenever a model field is added or a rule-pack band flips a verdict, because
`canonical_record_bytes` is `record.model_dump(mode="json")`, including the computed `verdict`.
`docs/technical/CAPABILITY_ROADMAP.md` discloses four such breaks (somatic FAIL floor, reproduce
slices 6 and 8, `RepairStep.detail`) and fixed none. Make verification independent of the current
model shape, so already-signed bundles keep verifying and tampering is still detected.

Candidate routes: verify over the bundle's stored raw JSON, or add a `canonical_version` with a
legacy path.

Caveats:
- Pre-existing signatures were made over bytes with then-current fields (including null ones), so
  the new scheme must reproduce them exactly.
- A new signed field would itself be a fifth break; put any new metadata in the unsigned
  `reproduce.json`.
- `exclude_none` is ruled out (breaks every RunRecord signature).

Tests first: a hand-signed old-shape fixture still verifies, a tampered field still fails, and the
four existing no-longer-verifies pins flip. Layer-2 (reproducibility); stdlib plus the existing
`cryptography` dependency; no new dependency.
