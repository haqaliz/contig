# C3 bio-plausibility, Phase 2 understanding

Grounded by a graphify-first code-mapping pass. File:line anchors are against the
worktree.

## The big finding (contradicts the brief, surfaced not papered over)

Much of what the C3 capability spec describes as future work **already exists in
the code** (CLAUDE.md: "code is ahead of the narrative docs"):

1. The rule schema **already supports two-sided bands**: `warn_above`/`fail_above`
   alongside `warn_below`/`fail_below`, evaluated by `_status_for`
   (`rule_pack.py:249-268`), with `_expected_range` formatting `[lo, hi]`. Tests
   exist (`tests/verification/test_rule_pack.py:122-166`). So a Ti/Tv or doublet
   band is expressible today, no schema work.
2. The germline pack **already declares the marquee plausibility checks**
   (`VARIANT_RULE_PACK`, `rule_pack.py:49-75`): `ts_tv_ratio` (metric `ts_tv`,
   band 1.5/1.8..2.4/3.0), `het_hom_ratio` (metric `het_hom`), `mean_coverage`.

## The real gap (where the actual work is)

`evaluate(metrics, pack)` (`rule_pack.py:282-301`) **skips any rule whose metric is
absent** from the ingested metrics (`if check["metric"] not in sample_metrics:
continue`). Metrics come only from MultiQC general-stats via
`parse_multiqc_general_stats_file` (`qc_ingest.py`). So the germline plausibility
rules **only fire if `ts_tv`/`het_hom`/`mean_coverage` are in sarek's MultiQC
general-stats**. They are most likely NOT (bcftools stats land in a separate
MultiQC section, not general-stats, and our parser reads general-stats only). If
so, **the germline plausibility rules are declared but dead.**

So the highest-value, most concrete slice is: **make the existing germline
plausibility rules actually fire** by computing `ts_tv` and `het_hom` (and
optionally coverage) **from the VCF**, then merging them into the metrics before
`evaluate()`. This directly reuses the deterministic VCF parser we just built for
concordance (`verification/concordance.py` `parse_vcf`), so it is testable the same
way (tiny inline VCF fixtures, no tool execution, no network).

Genuinely-missing checks for OTHER assays (not declared today): RNA-seq rRNA
contamination, scRNA-seq doublet rate. Those need both a new rule AND a metric
source, so they are later slices, not slice 1.

## Affected areas (confirmed)

- `src/contig/verification/rule_pack.py`, `VARIANT_RULE_PACK` (rules exist);
  `evaluate` skips absent metrics; `_status_for` already two-sided.
- `src/contig/verification/qc_ingest.py`, `parse_multiqc_general_stats[_file]`
  returns `{sample: {metric: float}}`. The merge point for VCF-derived metrics.
- `src/contig/verification/run_qc.py` `run_qc` / `evaluate_run_qc`, and
  `src/contig/runner.py:35 _discover_qc(run_dir, assay)`, where a per-assay pack is
  selected and evaluated; where VCF-derived germline metrics would be computed and
  merged before pack evaluation.
- `src/contig/verification/concordance.py` `parse_vcf`, the reusable VCF parser
  pattern for a `variant_metrics.py` (Ti/Tv, het/hom from genotypes).
- `QCResult.kind`: reuse `"metric"` (no new kind, no report/dashboard grouping
  change). The mapping agent confirmed a new kind would cost report.py + qc-panel.tsx
  changes for little benefit.

## Open questions for the interview

1. Slice 1 = compute germline Ti/Tv + het/hom from the VCF so the existing rules
   fire (recommended), vs starting with a different assay.
2. Whether to also compute `mean_coverage` (needs depth info, not just genotypes;
   may not be derivable from the VCF alone) or leave that rule metric-dependent.
3. Confirm the bands in the existing VARIANT_RULE_PACK are acceptable or need
   tuning, and the WARN/FAIL/UNVERIFIED policy (slice 1 likely keep the existing
   bands; an absent VCF or zero variants yields unverified, never a false pass).
4. Do we tune the rRNA/doublet checks now or defer to a later slice (recommend
   defer; slice 1 is germline-metrics-from-VCF).
