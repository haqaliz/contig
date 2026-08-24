# Spec — detector (aspect of runtime-reference-mismatch-detector)

> One-aspect slice (the `alignment_format_mismatch` template: one literal, one
> branch, one corpus family, one guard scenario, one taxonomy sync — one
> cohesive, test-first unit). Source: `docs/planning/runtime-reference-mismatch-detector/prd.md`.

## Problem slice

A hard-failing task whose log says the reads' contigs are absent from the
reference (e.g. STAR `sequence 'chr1' not found in the reference genome`, GATK
`Contig 'chr1' not found in the reference dictionary`) currently classifies
`tool_crash` at 0.4 (`src/contig/detect.py:434-445`). This aspect gives the
family its own class, seeds the corpus (golden + independently authored holdout
twin), guards the loop (heal-guard give-up), and mirrors the taxonomy to the
dashboard. No repair exists or is proposed — honest give-up, exactly like
`alignment_format_mismatch`.

## In-scope

- R1: `"reference_mismatch"` literal in `FailureClass` (`models.py:262-282`,
  19 → 20, after `alignment_format_mismatch`).
- R2: narrow AND-guarded branch after `alignment_format_mismatch`
  (`detect.py:414-432`), before `tool_crash` (`:434`), confidence 0.85.
  Primary phrase `not found in the reference` AND guard token
  (`contig` / `sequence` / `'chr`). Exact tuple pinned by the plan's tests.
- R3: one golden corpus case (`detector_corpus.jsonl`, 27 → 28, STAR wording).
- R4: one independently authored holdout twin
  (`detector_corpus_holdout.jsonl`, 14 → 15) + twin pin test
  (mirror `tests/test_eval_holdout.py:75-84`) + `eval-guard --update-baseline`
  refreeze (92.9% → 14/15 if it classifies; else disclosed known-miss).
- R5: one heal-guard give-up scenario (`heal_scenarios.jsonl`, 22 → 23,
  covered_classes 16 → 17) + `heal-guard --update-baseline` refreeze
  (outcome-match must stay 1.0) + pin-test updates
  (`tests/test_heal_scenarios.py:791-817`, new scenario test in
  `tests/test_heal_guard.py`).
- R6: dashboard sync (`derive.ts` FAILURE_CLASSES, `failure-classes.spec.ts`
  length 19 → 20 + PYTHON_ORDER, `promote-label-validation.spec.ts` round-trip);
  fix the already-stale heal-guard docstring (`cli.py:3079-3118`).
- R7: `tests/test_detect.py:331-337` flips positive (STAR contig-absence);
  `tests/test_detect.py:272-284` becomes a pinned control
  (GATK `incompatible contigs` → stays `tool_crash`); family controls added.
- R8: `qc_anomaly` non-overlap pin (success-path QC-FAIL stays `qc_anomaly`).
- R9: CHANGELOG entry (honesty clauses).

## Out-of-scope

Any repair/patch; the assembly-signature pre-flight form (blocked); GATK
`incompatible contigs` branch wording (excluded by decision — control negative);
C5 known-sites/GTF-version/RO-Crate; pin-conflict; verdict/exit-code changes;
real nf-core run in CI.

## Acceptance criteria (testable)

1. `diagnose_failure` classifies the STAR contig-absence log
   `reference_mismatch` at 0.85 with the matched line in evidence.
2. GATK `incompatible contigs` log stays `tool_crash` (pinned control).
3. `missing_index` / `missing_reference` logs keep their own classes
   (existing tests green, untouched behavior).
4. Training corpus 100% (28/28); holdout twin classifies (else disclosed
   known-miss); heal-guard outcome-match 1.0 over 23 scenarios;
   covered_classes == 17.
5. A success-path QC-FAIL run whose QC text contains the phrase is diagnosed
   `qc_anomaly`, never `reference_mismatch`.
6. Dashboard `FAILURE_CLASSES` has 20 entries in Python order; e2e pins green;
   promote round-trip accepts the new label.
7. Full suite green; no signature break (`tests/test_signing.py` precedent).

## Dependencies & sequencing

- Phase 1 (literal + branch + detect tests) precedes everything.
- Phases 2 (corpus + holdout) and 3 (heal scenario) are independent of each
  other after Phase 1 (distinct data files, distinct baseline files — safe to
  parallelize across agents).
- Phase 4 (non-overlap + safety net) after Phase 1.
- Phase 5 (dashboard) after Phase 1; Phase 6 (CHANGELOG + full suite) last.

## Open questions / risks

- 🔴 Reasoned-not-observed needle (self-graded fixtures; mitigated by the
  independent twin + the relabel→promote curation loop).
- 🟡 Over-match vs `missing_index`/`missing_reference` (AND-guard + controls).
- 🟡 GATK-phrase exclusion (revisit trigger: first real report).