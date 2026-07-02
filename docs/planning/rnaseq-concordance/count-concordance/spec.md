# Aspect spec — count-concordance

Single aspect of `rnaseq-concordance`. Full requirements live in
`../prd.md`; this spec is the buildable slice boundary.

## Problem slice & user outcome

Add a cross-tool quantification-concordance axis to the RNA-seq verdict: compare the
run's own gene-count matrix to a user-supplied second matrix and emit
`kind="concordance"` checks (Spearman, fraction-agreeing, informational gene-overlap),
WARN-capped, UNVERIFIED-never-PASS. User runs `contig verify <run>
--concordance-counts <matrix>` and sees whether two quantifiers agree — without the
result ever changing the verify exit code.

## In scope

- New module `src/contig/verification/count_concordance.py` (parser + hand-rolled
  Spearman + stats + `concordance_results` + `evaluate_count_concordance` gate).
- `run_qc` integration so a divergent rnaseq pair yields `verdict != "fail"`.
- `contig verify --concordance-counts <matrix>` (mutually exclusive with
  `--concordance-vcf` / `--concordance-auto`), exit-neutral.
- CHANGELOG + C1 capability markers.

## Out of scope

- Auto-running a second quantifier (deferred follow-on).
- Single-cell concordance; dashboard UI; threshold calibration / FAIL bands.
- Any change to germline `--concordance-vcf` behavior.

## Acceptance criteria (testable)

Mirror `../prd.md` §Acceptance Criteria 1–9. Headlines:
- concordant → PASS with metric; divergent → WARN, `verify` exit 0, `verdict != "fail"`.
- < 10 (or 0) shared genes → `spearman_concordance`/`fraction_agreeing` UNVERIFIED;
  `gene_overlap` still reports its value.
- zero/tiny counts don't crash (`|a−b|/max(a,b,1)`); duplicate ids sum; header skipped.
- `gene_overlap` never WARNs.
- non-rnaseq assay → `evaluate_count_concordance == []`; CLI skip note, exit unchanged.
- gzip parses; tolerant column layout parses; deterministic; no network.

## Dependencies & sequencing

Phase 1 (parser + Spearman) → Phase 2 (stats + results + gate) → Phases 3 (run_qc)
and 4 (CLI) in parallel → Phase 5 (docs). Test-first throughout. No new deps.

## Risks

Uncalibrated thresholds (WARN-capped, documented); real salmon column layout
unconfirmed from repo (tolerant parser + synthetic fixtures absorb it). See
`../prd.md` §Risks.
