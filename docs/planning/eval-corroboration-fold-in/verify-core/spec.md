# Aspect spec: verify-core

Slug: `eval-corroboration-fold-in` · Aspect: `verify-core`

## Problem slice

The labeling design + scoring core of the C6 fold-in: the `VerificationCase`
artifact (pre-band metric inputs → expected verdict), the pure scorer that
re-derives verdicts under the *current* rule packs (band-sensitive, never from
stored statuses), and the seeded synthetic holdout corpus with a forced
known-miss so the committed baseline is < 1.0. This aspect has no CLI and no
capture wiring — it is the pure machinery + data everything else consumes.

## In-scope

- `VerificationCase` + `VerifyEvalReport`/`VerifyCaseResult`/`VerifySnapshot`/
  `VerifyGuardResult` models (additive, optional-field back-compat).
- `src/contig/verify_corpus.py`: corpus I/O (load/save/append), the
  family→pack evaluator table, `evaluate_verify_case` (re-derivation),
  `evaluate_verify` (verdict-match rate + informational per-family rates),
  baseline save/load, `snapshot_from_verify_report`, `compare_verify_to_baseline`.
- Seed corpus `src/contig/data/verify_corpus_holdout.jsonl` (synthetic, ≥ 12
  cases, ids `verify-*`, `source="synthetic"`, disjoint from other corpora),
  including ≥ 1 known-miss case (R2a) so `verdict_match_rate < 1.0`.
- Threshold-sensitivity contract: a mutation test proves a band change flips a
  stored value's status (RED before GREEN).

## Out-of-scope

- CLI commands (aspect `verify-guard-command`), capture/promote (aspect
  `capture-promote`), dashboard work (aspect `failure-classes`).
- Band calibration itself; per-check labels; concordance-family capture
  (deferred by PRD R4a — but concordance status *derivation* from stored
  signal values IS in scope for the seed).

## Acceptance criteria

1. `evaluate_verify` over the committed holdout yields a deterministic
   `verdict_match_rate` (< 1.0, > 0.7) with per-family informational rates.
2. Mutation control: changing one band constant in a pack changes the predicted
   status of a case whose stored value crosses it (test, not prose).
3. Unlabeled cases (`expected_verdict=None`) are skipped, never counted wrong.
4. A family with no results for a case degrades that case to `unverified`
   predicted (never a false pass).
5. All existing suites stay green; no signed-field change.

## Dependencies / sequencing

First aspect (models are needed by everything). Needs `rule_pack.py` packs
importable (yes — the plausibility/composition packs are module constants).
`overall_verdict` (models.py:85-111) reused for reduction.

## Open questions

- Family naming: `multiqc`, `rnaseq_composition`, `rnaseq_plausibility`,
  `somatic_plausibility`, `annotation_plausibility`, `scrnaseq`, `germline`,
  `concordance` — the plan fixes the table.
