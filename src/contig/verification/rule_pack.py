"""RNA-seq QC rule pack + evaluator (ARCHITECTURE §6).

A rule pack is *data, not code*: a versioned, auditable list of checks the
verifier applies to ingested metrics. Keeping it declarative means a pack can be
diffed, pinned into a RunRecord, and tuned without code changes.

The thresholds below are illustrative, tunable engineering defaults for catching
gross run failures (e.g. a sample that barely aligned) -- they are not clinical
or biological claims.
"""

from __future__ import annotations

from contig.models import QCResult

RNASEQ_RULE_PACK: list[dict] = [
    {
        "check": "alignment_rate",
        "metric": "uniquely_mapped_percent",
        "warn_below": 60.0,
        "fail_below": 40.0,
        "message": "fraction of reads uniquely mapped to the reference",
    },
    {
        "check": "assignment_rate",
        "metric": "percent_assigned",
        "warn_below": 60.0,
        "fail_below": 40.0,
        "message": "fraction of reads assigned to features",
    },
    {
        # Real nf-core/rnaseq MultiQC reports the pseudo-alignment rate here
        # (Salmon general stats). This is the check that actually fires on real
        # runs; the two above key off synthetic/legacy metric names.
        "check": "salmon_mapping_rate",
        "metric": "percent_mapped",
        "warn_below": 60.0,
        "fail_below": 40.0,
        "message": "fraction of reads pseudo-aligned by Salmon",
    },
]


# Germline variant-calling QC for RESEARCH use (standard population-level metrics:
# Ti/Tv, het/hom, coverage). NOT clinical or diagnostic interpretation. The
# thresholds are illustrative, tunable engineering defaults -- a whole-genome
# germline Ti/Tv near ~2.0 is typical, so values far outside [1.5, 3.0] flag a
# likely run problem rather than a biological claim.
VARIANT_RULE_PACK: list[dict] = [
    {
        "check": "ts_tv_ratio",
        "metric": "ts_tv",
        "fail_below": 1.5,
        "warn_below": 1.8,
        "warn_above": 2.4,
        "fail_above": 3.0,
        "message": "transition/transversion ratio of called variants",
    },
    {
        "check": "het_hom_ratio",
        "metric": "het_hom",
        "fail_below": 1.0,
        "warn_below": 1.4,
        "warn_above": 2.5,
        "fail_above": 3.5,
        "message": "heterozygous/homozygous-alt genotype ratio",
    },
    {
        "check": "mean_coverage",
        "metric": "mean_coverage",
        "warn_below": 20.0,
        "fail_below": 10.0,
        "message": "mean depth of coverage across the callable genome",
    },
]


# Single-cell RNA-seq per-cell QC (nf-core/scrnaseq, STARsolo/Cell Ranger). These
# are per-sample summary metrics from the pipeline's MultiQC report (the STARsolo
# Summary.csv / Cell Ranger metrics_summary that MultiQC ingests). The metric keys
# below are the slugified names we read out of MultiQC general stats; the exact
# MultiQC slug can vary by aligner/version, so they are chosen to mirror the
# documented STARsolo/Cell Ranger fields (Estimated Number of Cells, Median Genes
# per Cell, Fraction Reads in Cells, % reads mapped to mitochondrial genes). The
# thresholds are illustrative, tunable engineering defaults for catching a grossly
# failed capture (almost no cells, near-empty droplets), not biological claims.
SCRNASEQ_RULE_PACK: list[dict] = [
    {
        "check": "estimated_cells",
        "metric": "estimated_cells",
        "warn_below": 500.0,
        "fail_below": 100.0,
        "message": "estimated number of cells recovered",
    },
    {
        "check": "median_genes_per_cell",
        "metric": "median_genes_per_cell",
        "warn_below": 500.0,
        "fail_below": 200.0,
        "message": "median genes detected per cell",
    },
    {
        "check": "fraction_reads_in_cells",
        "metric": "fraction_reads_in_cells",
        "warn_below": 0.7,
        "fail_below": 0.5,
        "message": "fraction of reads assigned to called cells (not ambient droplets)",
    },
    {
        "check": "pct_reads_mito",
        "metric": "pct_reads_mito",
        "warn_above": 20.0,
        "fail_above": 50.0,
        "message": "percent of reads mapping to mitochondrial genes",
    },
]


_RULE_PACKS: dict[str, list[dict]] = {
    "rnaseq": RNASEQ_RULE_PACK,
    "variant_calling": VARIANT_RULE_PACK,
    "scrnaseq": SCRNASEQ_RULE_PACK,
}


def rule_pack_for(assay: str) -> list[dict]:
    """Select the rule pack for an assay; unknown assays are a hard error."""
    try:
        return _RULE_PACKS[assay]
    except KeyError:
        raise ValueError(f"no rule pack for assay {assay!r}") from None


def _status_for(value: float, check: dict) -> str:
    """Apply optional lower and upper bounds; the worse status wins.

    Bounds are read with `.get()` so a check may declare any subset of
    {fail_below, warn_below, warn_above, fail_above}. Lower-bound-only checks
    (the existing RNA-seq packs) therefore behave exactly as before.
    """
    fail_below = check.get("fail_below")
    fail_above = check.get("fail_above")
    if (fail_below is not None and value < fail_below) or (
        fail_above is not None and value > fail_above
    ):
        return "fail"
    warn_below = check.get("warn_below")
    warn_above = check.get("warn_above")
    if (warn_below is not None and value < warn_below) or (
        warn_above is not None and value > warn_above
    ):
        return "warn"
    return "pass"


def _expected_range(check: dict) -> str:
    """Human-readable bound description for the QCResult, honoring whichever bounds exist."""
    warn_below = check.get("warn_below")
    warn_above = check.get("warn_above")
    if warn_below is not None and warn_above is not None:
        return f"[{warn_below}, {warn_above}]"
    if warn_above is not None:
        return f"<= {warn_above}"
    return f">= {warn_below}"


def evaluate(
    metrics: dict[str, dict[str, float]], rule_pack: list[dict]
) -> list[QCResult]:
    results: list[QCResult] = []
    for sample, sample_metrics in metrics.items():
        for check in rule_pack:
            if check["metric"] not in sample_metrics:
                continue
            value = sample_metrics[check["metric"]]
            status = _status_for(value, check)
            results.append(
                QCResult(
                    check=f"{check['check']}:{sample}",
                    status=status,
                    message=f"{sample}: {check['metric']}={value} ({status})",
                    value=value,
                    expected_range=_expected_range(check),
                )
            )
    return results
