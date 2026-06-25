# Aspect spec: germline-metrics (bio-plausibility slice 1)

Parent PRD: `../prd.md`. One buildable aspect: compute germline Ti/Tv and het/hom
from the VCF so the existing (currently dead) `VARIANT_RULE_PACK` plausibility
rules fire, capped at WARN, independent of MultiQC.

## Problem slice and outcome

A germline run's `ts_tv` and `het_hom` are computed deterministically from its VCF
and turned into QC checks that participate in the verdict (WARN at most). A run with
no VCF or an uncomputable ratio yields `unverified` for that check, never PASS.

## In scope
- `verification/variant_metrics.py`: deterministic `ts_tv` and `het_hom` from a VCF
  (reuse `concordance.parse_vcf`), each `None` when uncomputable.
- A germline plausibility evaluator emitting `QCResult`s (kind="metric"): pass/warn
  via the existing rule bands for computable metrics, explicit `unverified` for
  uncomputable ones.
- Edit `VARIANT_RULE_PACK` `ts_tv_ratio` and `het_hom_ratio` to WARN-only (drop
  fail bands); leave `mean_coverage` unchanged.
- Wire it on a path independent of the MultiQC early-return, gated to
  `variant_calling`; VCF value authoritative on a key collision; keyed by the VCF's
  primary sample.

## Out of scope
- rRNA / doublet / other-assay checks; coverage-from-VCF; multi-sample germline;
  FAIL severity; new QC kind; any dashboard/report change (kind="metric" already
  renders).

## Acceptance criteria (testable)
- `ts_tv`/`het_hom` match hand-computed values on inline VCF fixtures (SNV-only for
  ts_tv; het vs hom-alt genotypes for het_hom).
- A germline run with an out-of-band Ti/Tv yields a WARN `ts_tv_ratio` check; an
  in-band one yields PASS; never FAIL.
- No SNVs (ts_tv denominator 0) or no hom-alt (het_hom denominator 0) or no VCF
  yields `unverified` for that check; no crash, no PASS.
- The checks are produced even when there is NO MultiQC report (independent path).
- Full suite green (743 at branch point); `mean_coverage` behavior unchanged.

## Dependencies and sequencing
- Reuses `concordance.parse_vcf`. No external deps.
- Sequence: metric computation → plausibility evaluator + pack WARN cap → wiring.

## Open questions / risks
- A test may assert the old `VARIANT_RULE_PACK` FAIL bands; update it when capping.
- Multi-sample VCFs: primary sample only in slice 1 (documented).
