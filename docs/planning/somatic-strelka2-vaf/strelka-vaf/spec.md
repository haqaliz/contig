# Aspect spec: strelka-vaf

Single aspect of the `somatic-strelka2-vaf` feature. The feature PRD
(`../prd.md`) is the authoritative requirements source; this aspect covers all of it
(the feature is not decomposed further).

## Problem slice & outcome

Emit a distinct, WARN-capped `strelka_median_vaf:<sample>` QCResult on a somatic run,
derived natively from the Strelka2 call set's tier counts, firing **alongside** the
existing Mutect2 `median_vaf` as independent cross-caller corroboration.

## In scope

- Strelka2 tier-count VAF parser (SNV `AU/CU/GU/TU`, indel `TAR/TIR`; tier1).
- `TUMOR`-column resolver (Strelka2 has no `##tumor_sample=`).
- Pooled median across the SNV + indel files.
- A `strelka_median_vaf` rule in `SOMATIC_PLAUSIBILITY_PACK` + an evaluator mirroring
  `evaluate_somatic_plausibility` (`by_metric` → `evaluate` → `None`→UNVERIFIED).
- Gate wiring in `runner.py::_discover_qc` somatic block, reusing
  `somatic_concordance.select_caller_vcfs` to locate the Strelka2 pair.
- First committed synthetic Strelka2 FORMAT fixtures.

## Out of scope

Per PRD "Out of Scope": FAIL severity/calibration, swapped-pair smell test, PON wiring,
dashboard surface, any `FailureClass`/model/persisted-record/reproduce change.

## Acceptance criteria (testable)

- G1: both `median_vaf` (Mutect2) and `strelka_median_vaf` present for a two-caller run.
- G2: pooled median equals a hand-computed value on a known-tier fixture.
- G3: no Strelka VCF → silent skip; no `TUMOR` column / zero derivable VAFs / non-unique
  layout → one `strelka_median_vaf` UNVERIFIED (value None, kind metric); never a false pass.
- G4: full suite green (baseline 1539 passed, 1 skipped) + new tests; exit code unchanged;
  no other assay's verdict changes.

## Dependencies / sequencing

Parser (unit-tested) → evaluator + pack rule → gate wiring → full-suite + docs. No external
dependency; no model change.

## Aspect-specific risks

Tier-count formula correctness pinned only to synthetic fixtures (PRD R1/R5, accepted
eyes-open); `TUMOR`-column convention (PRD R2). Both bounded by the UNVERIFIED fallback.
