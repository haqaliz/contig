"""RNA-seq QC rule pack + evaluator (ARCHITECTURE §6).

A rule pack is *data, not code*: a versioned, auditable list of checks the
verifier applies to ingested metrics. Keeping it declarative means a pack can be
diffed, pinned into a RunRecord, and tuned without code changes.

The thresholds below are illustrative, tunable engineering defaults for catching
gross run failures (e.g. a sample that barely aligned); they are not clinical
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
# thresholds are illustrative, tunable engineering defaults; a whole-genome
# germline Ti/Tv near ~2.0 is typical, so values far outside [1.5, 3.0] flag a
# likely run problem rather than a biological claim.
VARIANT_RULE_PACK: list[dict] = [
    {
        # WARN-capped: these germline plausibility rules never FAIL a verdict in
        # this slice (the bands flag a likely run problem, not a clinical claim),
        # so they carry no fail_below/fail_above.
        "check": "ts_tv_ratio",
        "metric": "ts_tv",
        "warn_below": 1.8,
        "warn_above": 2.4,
        "message": "transition/transversion ratio of called variants",
    },
    {
        # WARN-capped (see ts_tv_ratio): no fail_below/fail_above.
        "check": "het_hom_ratio",
        "metric": "het_hom",
        "warn_below": 1.4,
        "warn_above": 2.5,
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


# Methyl-seq (bisulfite) per-sample QC (nf-core/methylseq, Bismark/bwa-meth).
# These are per-sample summary metrics from the pipeline's MultiQC report. The
# metric keys below mirror the documented Bismark fields MultiQC ingests; the
# exact MultiQC general-stats slug can vary by aligner/version, so they are
# chosen to track the documented quantities rather than a pinned slug:
#   percent_bs_conversion: bisulfite conversion rate (from the lambda/unmethylated
#       spike-in or non-CpG conversion); a low value means unconverted cytosines
#       masquerade as methylation. MultiQC slug unverified.
#   percent_aligned: Bismark mapping efficiency (% uniquely aligned). MultiQC
#       reports this as a Bismark general-stats column; slug unverified.
#   percent_duplication: % duplicate alignments removed by deduplicate_bismark.
# Thresholds are illustrative, tunable engineering defaults for catching a grossly
# failed run (poor conversion, almost nothing mapped, extreme duplication), not
# biological claims.
METHYLSEQ_RULE_PACK: list[dict] = [
    {
        "check": "bisulfite_conversion",
        "metric": "percent_bs_conversion",
        "warn_below": 98.0,
        "fail_below": 95.0,
        "message": "bisulfite conversion rate (unconverted C read as methylated below this)",
    },
    {
        "check": "mapping_efficiency",
        "metric": "percent_aligned",
        "warn_below": 50.0,
        "fail_below": 30.0,
        "message": "fraction of reads uniquely aligned by Bismark",
    },
    {
        "check": "duplication_rate",
        "metric": "percent_duplication",
        "warn_above": 50.0,
        "fail_above": 75.0,
        "message": "fraction of alignments flagged as duplicates",
    },
]


# 16S/ITS amplicon per-sample QC (nf-core/ampliseq, DADA2). Per-sample summary
# metrics from the pipeline's MultiQC report / DADA2 stats:
#   percent_retained: fraction of input reads surviving DADA2 filter+denoise+merge
#       +chimera removal; the headline "ran but wrong" signal for amplicon. The
#       exact MultiQC slug is unverified (DADA2 reports per-step counts that the
#       pipeline summarizes); we key off the documented retained-fraction quantity.
#   asv_count: number of ASVs inferred for the sample (too few means denoising
#       collapsed real diversity or the sample was near-empty). Slug unverified.
#   input_reads: raw read depth for the sample (a too-shallow sample cannot be
#       trusted regardless of retention). Slug unverified.
# Thresholds are illustrative, tunable engineering defaults, not biological claims.
AMPLISEQ_RULE_PACK: list[dict] = [
    {
        "check": "dada2_read_retention",
        "metric": "percent_retained",
        "warn_below": 50.0,
        "fail_below": 20.0,
        "message": "fraction of reads retained through DADA2 filtering and denoising",
    },
    {
        "check": "asv_count",
        "metric": "asv_count",
        "warn_below": 50.0,
        "fail_below": 10.0,
        "message": "number of ASVs (features) inferred for the sample",
    },
    {
        "check": "sample_read_depth",
        "metric": "input_reads",
        "warn_below": 10000.0,
        "fail_below": 1000.0,
        "message": "raw read depth for the sample",
    },
]


# Shotgun metagenomics per-bin/per-assembly QC (nf-core/mag). Assembly stats come
# from QUAST and bin quality from CheckM/BUSCO, both ingested by MultiQC:
#   n50: assembly contig N50 in bp; a tiny N50 is a fragmented (failed) assembly.
#       QUAST reports N50 in general stats; the MultiQC slug is unverified here.
#   completeness: CheckM bin completeness (%); how much of the expected single-copy
#       marker set the bin contains. MultiQC slug unverified.
#   contamination: CheckM bin contamination (%); marker duplication indicating the
#       bin mixes genomes. Lower is better, so this is an upper-bound check. Slug
#       unverified.
# Thresholds track the common CheckM "medium/high quality MAG" rules of thumb
# (completeness and contamination) and a coarse assembly-contiguity floor; they
# are illustrative, tunable engineering defaults, not biological claims.
MAG_RULE_PACK: list[dict] = [
    {
        "check": "assembly_n50",
        "metric": "n50",
        "warn_below": 5000.0,
        "fail_below": 1000.0,
        "message": "assembly contig N50 in base pairs",
    },
    {
        "check": "bin_completeness",
        "metric": "completeness",
        "warn_below": 70.0,
        "fail_below": 50.0,
        "message": "CheckM bin completeness (percent of expected marker genes)",
    },
    {
        "check": "bin_contamination",
        "metric": "contamination",
        "warn_above": 5.0,
        "fail_above": 10.0,
        "message": "CheckM bin contamination (percent marker duplication)",
    },
]


_RULE_PACKS: dict[str, list[dict]] = {
    "rnaseq": RNASEQ_RULE_PACK,
    "variant_calling": VARIANT_RULE_PACK,
    "scrnaseq": SCRNASEQ_RULE_PACK,
    "methylseq": METHYLSEQ_RULE_PACK,
    "ampliseq": AMPLISEQ_RULE_PACK,
    "mag": MAG_RULE_PACK,
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
