# Aspect spec: capture-promote

Slug: `eval-corroboration-fold-in` · Aspect: `capture-promote`

## Problem slice

The real-run channel: capture pre-band metric inputs into the run record
(additive optional field), append pending `VerificationCase`s for QC-driven
WARN/FAIL runs, and the `contig verify-case-promote` command that confirms or
corrects `expected_verdict` and moves cases into the golden corpus — the step
that makes the corpus non-tautological (PRD metric 5).

## In-scope

- `RunRecord.verification_inputs: dict[str, dict[str, dict[str, float]]] | None
  = None` (family → sample → metric → value), populated in `_discover_qc`
  (runner.py:285) where the metric dicts already exist, back-compat optional.
- Pending capture at the run finalize choke point: when the run's tasks all
  succeeded, `qc_results` non-empty, `overall_verdict(qc_results) in
  {"fail","warn"}`, and `verification_inputs` non-empty → append one
  `VerificationCase` to `<runs_dir>/pending_verify_corpus.jsonl`
  (`source="pending:{run_id}"`, `expected_verdict=None`, `known_miss=False`).
  Always on, no flag (qc_anomaly capture precedent).
- `contig verify-case-promote <case_id> --expected-verdict <v> [--pending
  <file>] [--golden <file>]`: find in pending, dedupe vs golden, rewrite
  `source` `pending:` → `confirmed:`, set `expected_verdict`, append to
  `src/contig/data/verify_corpus.jsonl`, remove from pending, echo. CLI-only
  (dashboard UI out of scope).
- Auto-snapshot on promote (corpus-promote precedent, cli.py:2403-2416): score
  the grown golden corpus and append a `VerifySnapshot` to `verify_history.jsonl`.

## Out-of-scope

- Dashboard pending-review UI for verification cases (deferred).
- Concordance-family capture (PRD R4a — seed-only in slice 1).
- Band calibration; per-check labels.

## Acceptance criteria

1. A real-shaped run record (injected fixtures) with QC FAIL/WARN verdict and
   captured inputs produces exactly one pending VerificationCase; a green PASS
   run produces none; a crashed run (failed events) produces none.
2. `verify-case-promote` round-trip: promote → case in golden with
   `source="confirmed:<run_id>"` and the corrected `expected_verdict`, removed
   from pending; second promote of the same id errors; unknown id errors.
3. Old bundles without `verification_inputs` load unchanged (back-compat test).
4. Promote writes an auto-snapshot to the history file.
5. Full suite green; no signed-field change.

## Dependencies / sequencing

Depends on aspect 1 (models + scorer + I/O). Aspect 2's guard is unaffected by
capture (guard scores the holdout; golden grows separately).
