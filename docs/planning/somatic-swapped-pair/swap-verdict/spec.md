# Aspect spec: swap-verdict

Parent PRD: `docs/planning/somatic-swapped-pair/prd.md`. Single aspect — the whole feature.

## Problem slice & user outcome

The somatic verdict reads VAF only from the tumor column, so a swapped/mislabeled/heavily-
contaminated normal passes silently. Outcome: the verdict gains one WARN-capped
`normal_median_vaf:<NORMAL>` check that fires when the normal column carries an implausibly
high median VAF (the somatic signal is in the normal), and degrades to UNVERIFIED — never a
false pass — when the normal column can't be resolved.

## In scope

- A `##normal_sample=` → `#CHROM` column resolver (new; none exists in-repo).
- `normal_median_vaf` = median VAF over the normal column, over the same biallelic Mutect2
  record set and same derivation the tumor `median_vaf` uses (FORMAT `AF`, else `AD_alt/DP`).
- One `normal_median_vaf` rule on `SOMATIC_PLAUSIBILITY_PACK`: `warn_above: 0.30`, no
  `warn_below`, no `fail_*`.
- `evaluate_swap_plausibility(vcf, sample=None)` emitting only that rule via the `by_metric`
  isolation trick (v0.34.0 strelka precedent).
- Runner wiring inside the existing `assay == "somatic_variant_calling"` block, on the
  already-located Mutect2 VCF.

## Out of scope

Per PRD "Out of Scope": FAIL severity/calibration, a directional ratio metric, PON wiring,
Strelka2-native normal VAF, a dashboard card, any `FailureClass`/self-heal/eval-corpus
change, any Layer-1 surface.

## Acceptance criteria (testable)

1. Correct pair (normal median VAF ≤ 0.10) → **PASS** `normal_median_vaf:<NORMAL>`.
2. Swapped/high-normal pair (normal median VAF ~0.45) → **WARN** `normal_median_vaf:<NORMAL>`,
   message naming swap/mislabel/contamination.
3. `##normal_sample=` absent/unparseable, or normal column present but no derivable VAF →
   **UNVERIFIED** (never PASS, never silently dropped).
4. The evaluator emits **only** the `normal_median_vaf` check — never re-emits
   `median_vaf`/`somatic_variant_count`/`strelka_median_vaf`.
5. Gzip (`*.vcf.gz`) supported.
6. Wired into `run_qc` for a somatic run; **never changes the `contig run`/`verify` exit
   code**. Full suite green, no regression.

## Dependencies & sequencing

Self-contained; all seams exist (`_vaf_from_sample`, `_biallelic`, `SOMATIC_PLAUSIBILITY_PACK`,
`evaluate()`, `select_caller_vcfs`, the somatic runner block). No new dependency.

## Open questions / risks

- `##normal_sample=` header spelling — confirmed emitted by GATK Mutect2; UNVERIFIED floor
  absorbs any deviation. No real sarek/GATK run in CI.
- Band `warn_above: 0.30` is an uncalibrated engineering default (accepted, WARN-only).
