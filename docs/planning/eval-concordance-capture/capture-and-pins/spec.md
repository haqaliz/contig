# Aspect spec: capture-and-pins

Parent PRD: `../prd.md`. Single aspect for this slice (small, cohesive): the whole
PRD (M1–M6, S1, N1) is one buildable unit.

## Problem slice & user outcome

A WARN/FAIL somatic or annotation run appends a pending verification case whose
`inputs` today carry none of the families that flagged it (concordance + the two
plausibility gaps are scoreable in the guard but never captured). After this aspect
the pending case is self-describing: its pre-band inputs cover every run-dir-derived
corroboration family, and `verify-guard` re-derivation covers them per-kind.

## In scope

1. Stats out-params (the `capture_metrics=` precedent, `variant_metrics.py:151-192`)
   on `evaluate_somatic_concordance` / `evaluate_somatic_concordance_from_run` and
   `evaluate_consequence_concordance` / `_evaluate_both_metrics` /
   `evaluate_annotation_concordance_from_run`, emitting `{"value", "n_shared"}` per
   pair key (`mutect2_vs_strelka2`, `vep_vs_snpeff`), raw values, written on both the
   normal and the too-few-sites paths.
2. `capture_inputs` writes in `_discover_qc`: `concordance_somatic_overlap`
   (somatic branch), `concordance_consequence` (VARIANT_ASSAYS branch),
   `somatic_plausibility` (median_vaf / somatic_variant_count /
   strelka_median_vaf / normal_median_vaf), `annotation_plausibility`
   (annotation_real_fraction / annotation_consequence_distribution).
3. Round-trip and per-kind status-consistency pins (M5), message-stability pins
   (M5b), family-key enumeration (N1).
4. Docs (M6): `verify_corpus.py:80-82` comment, `runner.py:296-300` docstring,
   CHANGELOG Unreleased, CAPABILITY_ROADMAP.md C6/C1, S1 revisit-trigger text.

## Out of scope

- Germline / RNA-seq / single-cell concordance capture (S1: deferred, revisit
  trigger committed).
- `fraction_agreeing` / `gene_overlap` / `gene_symbol_concordance` guard families
  (no scorer family exists).
- FAIL severity / band calibration; any dashboard or CLI surface; any new
  dependency; any signature/model change.

## Acceptance criteria (testable)

- **AC1** `_discover_qc` on a synthetic somatic run dir (Mutect2 + Strelka2 PASS
  VCFs) writes `capture_inputs["concordance_somatic_overlap"] =
  {"mutect2_vs_strelka2": {"value": <raw jaccard>, "n_shared": <union>}}`.
- **AC2** The same branch writes `somatic_plausibility` with the numeric metrics
  (no `pon_applied`), keyed as the check names key.
- **AC3** `_discover_qc` on a synthetic annotated variant run (single-vcf-both or
  two-file layout) writes `concordance_consequence` + `annotation_plausibility`.
- **AC4** A too-few-sites concordance case (union < 10 / shared < 10) is still
  captured with raw values; re-derivation gives `unverified`, matching the QCResult.
- **AC5** Round-trip: a pending case built from a WARN/FAIL synthetic somatic run
  carries all four families; `evaluate_verify_case` re-derives each family's status
  equal to the QCResult's status for that family (per-kind pin).
- **AC6** Emitted QCResult messages are byte-identical after the out-param
  refactors (existing wiring tests unchanged).
- **AC7** Family-key enumeration test lists exactly the four new keys; a fifth is
  a deliberate act.
- **AC8** Suite green; `verify-guard` / `eval-guard` / `heal-guard` baselines
  unmoved (no corpus/holdout/baseline edit); no new dependency; no real nf-core
  run or network in CI.

## Dependencies & sequencing

Phase 1 (somatic) and Phase 2 (annotation) are independent → parallelizable.
Phase 3 (round-trip/consistency pins) depends on both. Phase 4 (docs) last.
Guard side (`verify_corpus.py`) is untouched — it already resolves all four families.

## Open questions / risks

- Exact metric-dict keys inside `evaluate_somatic_plausibility` /
  `evaluate_swap_plausibility` / `evaluate_strelka_vaf_plausibility` /
  `evaluate_annotation_plausibility` must be mirrored from each module's own
  `by_metric` construction (annotation_plausibility.py:267-272; the somatic
  equivalents read at implementation time) — never re-derived in the runner.
- Sample-key convention for the plausibility families: mirror
  `evaluate_variant_plausibility`'s capture keying (variant_metrics.py:191-192);
  the pinning test fixes the actual key.
- `n_shared` is an int but the `verification_inputs` contract is float-valued —
  store `float(union)` / `float(shared)`.
