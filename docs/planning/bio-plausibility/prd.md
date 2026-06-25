# PRD: Biological-plausibility verification (C3, germline slice)

Status: draft for review. Owner: aliz. Branch: `feat/bio-plausibility/aliz`.
Sources: `docs/planning/_card/issue.md`, `docs/planning/_card/understanding.md`,
`docs/technical/CAPABILITY_ROADMAP.md` (C3).

## Problem Statement

Contig's germline rule pack already *declares* the marquee biological-plausibility
checks (`VARIANT_RULE_PACK` in `rule_pack.py`): transition/transversion ratio
(`ts_tv`), heterozygous/homozygous ratio (`het_hom`), and mean coverage. But these
rules are **dead**: `evaluate()` skips any rule whose metric is absent from the
ingested MultiQC general-stats, and `ts_tv`/`het_hom` are not in sarek's
general-stats (bcftools stats land in a separate MultiQC section our parser does
not read). So today the verdict **silently ignores** a wildly-off Ti/Tv, which is a
hallmark of a broken germline call set. That is a false sense of safety: a run can
read PASS while its variant biology is implausible.

This slice makes the existing germline plausibility rules **actually fire** by
computing `ts_tv` and `het_hom` directly from the run's VCF (reusing the
deterministic parser built for concordance) and feeding them into the verdict.

## Goals & Success Metrics

- `ts_tv` and `het_hom` are computed deterministically from a germline VCF and
  merged into the metrics so the existing `VARIANT_RULE_PACK` rules evaluate. No
  tool execution, no network; tested on tiny inline VCF fixtures.
- A germline run whose Ti/Tv or het/hom falls outside the plausible band yields a
  **WARN** (never FAIL in this slice) naming the check, the value, and the band.
- A run with no VCF, or zero comparable SNVs, yields **unverified** for these
  checks, never a false PASS and never a divide-by-zero.
- Zero regression to the 743 passing tests; `mean_coverage` behavior unchanged.
- The activated checks appear in the verdict, `contig show`, and the reports like
  any other metric check (reuse `kind="metric"`).

## User Personas & Scenarios

- **A, lone computational biologist**: runs germline calling and wants the verdict
  to flag "your Ti/Tv is 1.1, this call set looks wrong" instead of silently
  passing on output-presence and mapping rate alone.
- **C, core facility**: wants a consistent biological sanity gate a non-expert PI
  can read, not just file-integrity checks.
- **D, biotech researcher**: wants the plausibility figure and its band recorded in
  provenance for the Methods trail.

## Requirements

### Must-have (this slice)
- A deterministic metric computation (new `verification/variant_metrics.py`, or an
  extension reusing `concordance.parse_vcf`) that, from a germline VCF, computes:
  - `ts_tv`: transitions / transversions over biallelic SNV sites (indels and
    multiallelic sites excluded from the ratio).
  - `het_hom`: count of heterozygous genotypes / count of homozygous-alt genotypes.
- The computed metrics are merged into the per-sample metrics dict (keyed by the
  VCF's sample) before `evaluate()` runs, so the existing rules fire.
- The activated `ts_tv_ratio` and `het_hom_ratio` checks are **capped at WARN** for
  this slice: their FAIL bands are removed (kept as WARN bands), so we never
  false-FAIL on an uncalibrated band. A comment records that FAIL returns after
  real-data calibration.
- Empty/edge handling: no VCF, zero SNVs (ts_tv denominator zero), or zero hom-alt
  (het_hom denominator zero) yields `unverified` for that specific check, never a
  crash and never PASS.
- Wiring: the germline path (`runner.py:_discover_qc(run_dir, assay="variant_calling")`
  or `run_qc`) computes the VCF metrics and merges them, gated to the germline
  assay only; other assays untouched.
- **Independent of MultiQC** (gap 1, critical): `evaluate_run_qc` returns `[]` when
  MultiQC general-stats is empty/absent. The VCF-derived plausibility checks MUST be
  computed and evaluated on their own path, NOT inside that early-return, so a
  germline run with a VCF but no (or no variant-section) MultiQC still gets the
  checks. These are exactly the runs the feature targets.
- **Precedence** (gap 2): when both the VCF computation and MultiQC general-stats
  carry `ts_tv`/`het_hom`, the **VCF-computed value is authoritative** for the
  activated checks (it is what we control and test deterministically). Document it
  at the merge.
- **Sample key** (gap 3): the VCF-derived metrics are keyed by the VCF's primary
  sample name; if that sample is unnamed, use a single stable synthetic key. Slice 1
  computes for the primary sample only, so the checks read `ts_tv_ratio:<sample>`
  without doubling the sample axis.

### Should-have
- The computed `ts_tv`/`het_hom` values recorded so the result is auditable and
  reproducible.

### Nice-to-have (explicitly later slices, not now)
- RNA-seq rRNA-contamination and scRNA-seq doublet-rate checks (need new rules and
  metric sources).
- Coverage derived from the VCF (DP), and multi-sample germline handling beyond the
  primary sample.
- Promoting the bands to FAIL once calibrated on real data.

## Technical Considerations

- **Reuse the concordance VCF parser**: `concordance.parse_vcf` already yields
  `{(CHROM,POS,REF,ALT): normalized_gt}`. `ts_tv` needs REF/ALT (single-base for
  SNVs); `het_hom` needs the GT. Both are available from that output, so the new
  metric function can reuse it or parse minimally the same way.
- **Verdict integration is free**: a plausibility `QCResult` is `kind="metric"`
  and flows through `overall_verdict` unchanged. No new kind (the mapping pass
  confirmed a new kind would cost report.py + dashboard grouping for little gain).
- **Merge point**: VCF-derived metrics are added to the `{sample: {metric: value}}`
  dict (from `parse_multiqc_general_stats_file`, possibly empty) before `evaluate`,
  and `evaluate` over the germline pack is run for them even when that dict was
  empty (the independent path above). The VCF value wins on a key collision.
- **WARN cap**: edit the `ts_tv_ratio` and `het_hom_ratio` entries in
  `VARIANT_RULE_PACK` to drop `fail_below`/`fail_above`, keeping `warn_below`/
  `warn_above`. `_status_for` already tolerates missing bound keys.
- **Determinism / reproducibility**: pure function of the VCF bytes; no randomness,
  no tool run. The computed values belong in the record like any QC metric.
- **Verification honesty**: conservative (WARN cap), unverified when inputs are
  absent, preserving the near-zero false-pass guarantee.

## Data Model / Artifact Contracts

- No model change. Reuses `QCResult` (`kind="metric"`, status in pass/warn/
  unverified). Check names stay `ts_tv_ratio:<sample>` and `het_hom_ratio:<sample>`
  from the existing rules.

## Risks & Open Questions

- **Incorrect metric computation** (Ti/Tv or het/hom): mitigated by test-first
  fixtures with hand-computed expected ratios, including SNV-only filtering.
- **Multi-sample VCFs**: slice 1 computes for the primary sample (matching how
  `parse_vcf` reads the first sample); multi-sample is a later slice. Flagged.
- **Uncalibrated bands**: mitigated by WARN-only; FAIL deferred.
- **Indel/multiallelic representation**: ts_tv counts biallelic SNVs only;
  documented, not silently mishandled.
- Resolved (gap 1): VCF plausibility runs on a path independent of the MultiQC
  early-return, so a VCF-but-no-MultiQC germline run still gets the checks.
- Resolved (gap 2): the VCF-computed value is authoritative on a key collision.
- Resolved (gap 3): metrics keyed by the VCF's primary sample (synthetic key if
  unnamed); primary sample only in slice 1.

## Out of Scope

- rRNA / doublet / other-assay plausibility checks.
- Coverage from the VCF; multi-sample germline beyond the primary sample.
- FAIL-severity plausibility.
- Any clinical interpretation of Ti/Tv or genotype ratios.
