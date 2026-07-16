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
        # The FAIL bands are gross-implausibility engineering tripwires (same tier
        # as mean_coverage's fail_below): a call set this far off a real germline
        # Ti/Tv (~2.0 WGS, up to ~3.0-3.3 WES) is almost certainly broken, not a
        # biological/clinical claim. Deliberately WES-safe — fail_above 3.6 leaves
        # exome Ti/Tv comfortably inside WARN. The WARN band (1.8-2.4) still flags
        # the softer "unusual, check it" range between the FAIL bounds.
        "check": "ts_tv_ratio",
        "metric": "ts_tv",
        "fail_below": 1.2,
        "warn_below": 1.8,
        "warn_above": 2.4,
        "fail_above": 3.6,
        "message": "transition/transversion ratio of called variants",
    },
    {
        # Gross-implausibility FAIL bands (see ts_tv_ratio): a het/hom this far from
        # the typical germline range flags a broken call set, WES-safe and not a
        # clinical claim. WARN band (1.4-2.5) covers the softer range.
        "check": "het_hom_ratio",
        "metric": "het_hom",
        "fail_below": 1.0,
        "warn_below": 1.4,
        "warn_above": 2.5,
        "fail_above": 3.0,
        "message": "heterozygous/homozygous-alt genotype ratio",
    },
    {
        # fail_below 1 is a hard floor: an empty/near-empty call set (0 sites) is a
        # broken run and FAILs, same tier as mean_coverage's fail_below. There is
        # deliberately NO fail_above — warn_above stays a SOFT, uncalibrated
        # "absurd-count" tripwire, NOT a validated ceiling, so a very large
        # joint-called cohort tripping it is an honest "unusually large, check it"
        # WARN, never a block.
        "check": "variant_count",
        "metric": "variant_count",
        "fail_below": 1,
        "warn_below": 10,
        "warn_above": 20_000_000,
        "message": "number of distinct germline variant sites (primary sample)",
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
# per Cell, Fraction Reads in Cells). The thresholds are illustrative, tunable
# engineering defaults for catching a grossly failed capture (almost no cells,
# near-empty droplets), not biological claims.
# Deferred, deliberately NOT shipped here: mitochondrial-read fraction and
# doublet rate. Both need a downstream scanpy/scDblFinder step that the base
# nf-core/scrnaseq pipeline does not run, so its MultiQC report never carries
# them; wiring a check against a metric the pipeline never emits would be dead
# and misleading. Add them only once that downstream step is part of the run.
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
]


# Methyl-seq (bisulfite) per-sample QC (nf-core/methylseq, Bismark). Metrics are
# ingested by a DEDICATED gate (`runner._discover_qc`, `assay == "methylseq"`)
# that parses Bismark's own on-disk report artifacts directly via
# `verification/methylseq_metrics.py` — NOT MultiQC general-stats, whose slug
# for these fields is not reliably stable across aligner/version (see
# `_DEDICATED_METRIC_ASSAYS` in runner.py, the methylseq-firing slice):
#   percent_aligned: Bismark mapping efficiency (% uniquely aligned pairs/reads),
#       from the `Mapping efficiency:` line of the alignment report
#       (`*_PE_report.txt` / `*_SE_report.txt`).
#   percent_duplication: % duplicate alignments removed, from the
#       `... duplicated alignments removed:` line (with its parenthesized
#       percent) of the deduplication report (`*.deduplication_report.txt`,
#       written by `deduplicate_bismark`).
#   percent_bs_conversion: bisulfite conversion rate (from a lambda/unmethylated
#       spike-in or other control); a low value means unconverted cytosines
#       masquerade as methylation. **Control-dependent**: a standard Bismark
#       splitting report carries methylation-context percentages only, with NO
#       conversion-rate field, so this metric is emitted only when a
#       recognizable conversion/control line is present — otherwise it is
#       correctly OMITTED (the check simply produces no result for that sample,
#       never a guessed value; see methylseq_metrics.parse_bismark_conversion_report).
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


# 16S/ITS amplicon per-sample QC (nf-core/ampliseq, DADA2). The exact MultiQC
# general-stats slug for these metrics is unverified (DADA2 reports per-step
# counts that the pipeline summarizes, not a stable general-stats field), so
# `runner._discover_qc`'s ampliseq gate ingests DADA2's own on-disk stats
# artifacts directly via `verification/ampliseq_metrics.py`, bypassing MultiQC
# entirely (see `_DEDICATED_METRIC_ASSAYS`). Per-metric DADA2 source:
#   percent_retained: fraction of input reads surviving DADA2 filter+denoise
#       +merge+chimera removal; the headline "ran but wrong" signal for
#       amplicon. Computed as nonchim / input * 100 from DADA2's
#       `overall_summary.tsv` track table (`parse_dada2_overall_summary`).
#   asv_count: number of ASVs inferred for the sample (too few means denoising
#       collapsed real diversity or the sample was near-empty). Computed as
#       the count of non-zero rows in the sample's column of the ASV table
#       (`*ASV_table*`, `parse_asv_table`).
#   input_reads: raw read depth for the sample (a too-shallow sample cannot be
#       trusted regardless of retention). Read straight from the `input`
#       column of `overall_summary.tsv` (`parse_dada2_overall_summary`).
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


# Shotgun metagenomics per-bin QC (nf-core/mag). The exact MultiQC
# general-stats slug for these metrics is unverified (QUAST/CheckM report
# per-assembly/per-bin fields that the pipeline summarizes, not a stable
# general-stats field), so `runner._discover_qc`'s mag gate ingests QUAST's
# and CheckM's own on-disk stats artifacts directly via
# `verification/mag_metrics.py`, bypassing MultiQC entirely (see
# `_DEDICATED_METRIC_ASSAYS`). The entity key is the BIN, not the sample.
# Per-metric source:
#   n50: assembly contig N50 in bp; a tiny N50 is a fragmented (failed)
#       assembly. Read from the `N50` column of QUAST's
#       `transposed_report.tsv` (`parse_quast_report`).
#   completeness: CheckM bin completeness (%); how much of the expected
#       single-copy marker set the bin contains. Read from the `Completeness`
#       column of CheckM's summary table (`parse_checkm_summary`).
#   contamination: CheckM bin contamination (%); marker duplication
#       indicating the bin mixes genomes. Lower is better, so this is an
#       upper-bound check (`warn_above`/`fail_above`). Read from the
#       `Contamination` column of CheckM's summary table
#       (`parse_checkm_summary`).
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


# RNA-seq biological-plausibility checks (capability C3, RNA-seq slice).
#
# This pack is now MIXED-UNIT and MIXED-VERIFICATION-STATUS on purpose — the
# two rules below share a pack, not a code path or a provenance story:
#
#   duplication_rate (PERCENT_DUPLICATION, Picard MarkDuplicates via MultiQC):
#     VERIFIED slug and unit, from source, not from an observed run: MultiQC
#     republishes Picard's own field name verbatim, and it is uppercase
#     (PERCENT_DUPLICATION), not the lowercase percent_duplication this pack
#     used to key on. Picard's javadoc is explicit that the value is "the
#     fraction of mapped sequence that is marked as duplicate" — a raw 0-1
#     fraction, with no x100 anywhere in its formula, despite the "PERCENT" in
#     its name. This is UNLIKE METHYLSEQ_RULE_PACK's percent_duplication,
#     which genuinely is 0-100: that parser reads Bismark's own parenthesized
#     percent text ("duplicated alignments removed: N (12.34%)", see
#     methylseq_metrics.py:81-84). The two slugs share a name and nothing
#     else — never assume one's scale from the other.
#     NO BAND: informational only, always pass when in [0, 1]. A deep/
#     high-input library legitimately exceeds 90% duplication (real science),
#     so any warn/fail band here would flag a legitimate protocol, not a
#     broken run — see the biology reason below, which still applies. A band
#     becomes justifiable only if real per-protocol duplication distributions
#     are collected, or the pack gains a library-prep/input-amount signal that
#     could separate "deep library" from "broken library"; neither exists
#     today. The "unit": "fraction" key below drives a guard in
#     evaluate_rnaseq_plausibility: a value PRESENT but outside [0, 1] (e.g. a
#     pre-scaled 95.0) is refused as unverified, never rescaled — a value like
#     0.5 would be ambiguous between "50%" and "0.5%", so guessing would be
#     worse than refusing.
#     No real nf-core/rnaseq multiqc_data.json exists in this repo to confirm
#     the key against (demo/sample-run's is synthetic; see
#     demo/make_sample_run.py:59,105) — the key and unit above are read from
#     MultiQC's and Picard's own source, not from an observed report.
#
#   rrna_contamination (percent_rRNA, featureCounts rRNA biotype):
#     Slug UNVERIFIED — a best-effort guess, never confirmed against a real
#     report (demo/sample-run/results/multiqc/multiqc_data.json carries only
#     uniquely_mapped_percent, percent_assigned, total_reads; this rule has
#     never once fired on a real report). Declared scale 0-100.
#     WARN-capped BY DECISION, not pending calibration: total-RNA /
#     ribo-depletion protocols legitimately retain rRNA, so "extreme" and
#     "unusual protocol" are the same number here too — the biology reason
#     duplication_rate no longer needs still applies to this metric.
#
# Neither rule carries a fail band, for the two independent per-metric reasons
# documented above — this is no longer one shared policy statement.
RNASEQ_PLAUSIBILITY_PACK: list[dict] = [
    {
        "check": "duplication_rate",
        "metric": "PERCENT_DUPLICATION",   # Picard MarkDuplicates via MultiQC; verified
        # Honored ONLY by evaluate_rnaseq_plausibility's guard, not by the
        # shared evaluate() — declaring "unit" on another pack is a no-op.
        "unit": "fraction",                # raw 0-1 fraction; see header — no x100
        "message": (
            "fraction of alignments flagged as duplicates (0-1; Picard "
            "PERCENT_DUPLICATION via MultiQC)"
        ),
    },
    {
        "check": "rrna_contamination",
        "metric": "percent_rRNA",          # featureCounts rRNA biotype; slug unverified
        "warn_above": 10.0,                # high => poor rRNA depletion
        "message": "fraction of reads assigned to the rRNA biotype",
    },
]


# Somatic (tumor-normal) biological-plausibility checks (capability C4 follow-on).
# Mixed severity, deliberately: somatic_variant_count carries a fail_below: 1
# floor that fires when no biallelic records were called (an empty or truncated
# call set is a broken run — an engineering tripwire, not a biological or
# clinical claim), while BOTH VAF metrics are WARN-capped BY DECISION, not
# pending calibration. See each rule's comment for its reason; the short
# version is that a tumor VAF has no protocol-independent expected value the
# code can observe, so no fail band on it can be honest.
# The bands are otherwise illustrative, tunable engineering defaults, NOT
# biological claims. Computed from the tumor column of the Mutect2 somatic VCF
# (AF else AD/DP); UNVERIFIED-when-uncomputable absorbs a non-Mutect2 / stripped
# VCF (see evaluate_somatic_plausibility). Like the germline/RNA-seq plausibility
# packs, this is imported directly by its evaluator and is deliberately NOT
# registered in _RULE_PACKS.
SOMATIC_PLAUSIBILITY_PACK: list[dict] = [
    {   # tumor VAF distribution: a somatic set spans low subclonal to ~0.5 clonal-het;
        # a median pinned near 1.0 (germline leakage) or ~0.5 (mis-paired normal) is
        # suspicious. WARN-capped BY DECISION — do not add a fail band here.
        # Germline Ti/Tv could ship FAIL bands because its expected value is
        # physically constrained (~2.0 WGS, ~3.0-3.3 WES) with noise at a
        # distinguishable ~0.5. Tumor VAF has no such structure: its expected
        # value is a function of purity and clonality, NEITHER OF WHICH THIS CODE
        # EVER OBSERVES (no purity estimate, no ploidy, no copy-number, no target
        # type). A low median VAF is legitimate science — a low-purity tumor or a
        # subclonal population — so any fail_below would FAIL a real sample. The
        # bands stay soft, uncalibrated engineering defaults.
        "check": "median_vaf",
        "metric": "median_vaf",
        "warn_below": 0.05,
        "warn_above": 0.95,
        "message": "median tumor variant allele fraction",
    },
    {   # fail_below 1 is a hard floor: no biallelic records called (an empty or
        # truncated call set — count is incremented only for biallelic records,
        # see somatic_plausibility.py) is a broken run and FAILs, same
        # engineering tier as mean_coverage's fail_below — not a biological or
        # clinical claim. There is deliberately NO fail_above: warn_above stays
        # a SOFT, uncalibrated "absurd-count" tripwire, never a validated
        # ceiling, because a hypermutator (MSI-high, POLE-mutant) or a WGS
        # tumor legitimately exceeds it. The band is otherwise coarse because
        # target type (panel/WES/WGS) varies by orders of magnitude.
        "check": "somatic_variant_count",
        "metric": "somatic_variant_count",
        "fail_below": 1,
        "warn_below": 10,
        "warn_above": 100000,
        "message": "number of somatic variant records called",
    },
    {   # Strelka2's own tier1-count VAF (see strelka_vaf.py), NOT the Mutect2
        # AF/AD-DP metric above. Reuses median_vaf's band verbatim: same
        # uncalibrated engineering default, shared across both callers rather
        # than re-derived. WARN-capped BY DECISION — do not add a fail band here.
        # It inherits median_vaf's reason above (a tumor VAF's expected value
        # depends on unobserved purity/clonality), and adds one of its own: a
        # fail_above: 1.0 would be DEAD CODE FOR EVERY REAL INPUT, because this
        # metric is arithmetically bounded to [0,1] given non-negative tier
        # counts (which the VCF spec guarantees) — strelka_vaf.py:95-98 and
        # :121-124 reject denom <= 0, and the numerator is one of the two
        # summands, so a tier1 ratio can never exceed 1.
        # Evaluated by its own
        # evaluate_strelka_vaf_plausibility() over a by_metric dict containing
        # ONLY this key, so this rule fires without ever re-emitting the two
        # Mutect2 rules above (evaluate() skips any rule whose metric is absent
        # from the sample dict).
        "check": "strelka_median_vaf",
        "metric": "strelka_median_vaf",
        "warn_below": 0.05,
        "warn_above": 0.95,
        "message": "median tumor variant allele fraction (Strelka2 tier1 counts)",
    },
]


# Annotation consequence-distribution plausibility (capability C7, M3). WARN-capped
# (no fail_*): the bands are illustrative, tunable engineering defaults, NOT
# biological claims, uncalibrated on real cohorts. Computed over annotated
# records from the CSQ/ANN consequence parse (see annotation_plausibility.py);
# UNVERIFIED-when-uncomputable absorbs an unresolvable CSQ Format or a VCF with
# no annotated records (see evaluate_annotation_plausibility). Like the other
# plausibility packs, this is imported directly by its evaluator and is
# deliberately NOT registered in _RULE_PACKS.
ANNOTATION_PLAUSIBILITY_PACK: list[dict] = [
    {   # a degenerate run: almost every variant is empty or intergenic. Loose
        # floor so a legit high-intron/UTR run does not trip it.
        "check": "annotation_real_fraction",
        "metric": "real_consequence_fraction",
        "warn_below": 0.10,
        "message": (
            "few variants received a real (non-intergenic) consequence — "
            "annotation may be degenerate"
        ),
    },
    {   # the PRD's "~100%-intergenic" smell; loose ceiling so a real
        # high-intergenic WGS/off-target run still passes.
        "check": "annotation_consequence_distribution",
        "metric": "intergenic_fraction",
        "warn_above": 0.95,
        "message": (
            "nearly all variants are intergenic — check the reference/"
            "annotation cache"
        ),
    },
]


# RNA-seq read-composition plausibility (C3). Fractions in [0,1] (NOT the 0-100
# percent scale of the MultiQC packs), so the bands are fractions too.
# WARN-capped BY DECISION, not pending calibration. Do not add a fail band here.
# Every metric below has a legitimate protocol occupying its extreme: a
# nuclear/FFPE/3'-biased library is legitimately intron-dominated (so a low
# exonic_fraction and a high intronic_fraction are both real science), and a
# non-model or sparse annotation legitimately leaves most tags unassigned.
# "Extreme" and "unusual protocol" are the same number, and the pack sees no
# library-prep or annotation-quality signal that could tell them apart.
# Separately, the one genuinely broken case — unassigned_fraction == 1.0 — is
# already caught more honestly by RNASEQ_RULE_PACK's assignment_rate
# fail_below: 40 on the did-it-run tier, so a fail band here would be redundant
# rather than new signal. Uncalibrated engineering defaults; evaluated by the
# dedicated read_distribution gate in runner._discover_qc and deliberately NOT
# registered in _RULE_PACKS.
RNASEQ_COMPOSITION_PACK: list[dict] = [
    {
        "check": "exonic_fraction",
        "metric": "exonic_fraction",
        "warn_below": 0.50,
        "message": "fraction of assigned reads in exons (CDS+UTRs); low suggests gDNA "
        "contamination or failed enrichment",
    },
    {
        "check": "intronic_fraction",
        "metric": "intronic_fraction",
        "warn_above": 0.30,
        "message": "fraction of assigned reads in introns; high suggests pre-mRNA / gDNA "
        "contamination",
    },
    {
        "check": "unassigned_fraction",
        "metric": "unassigned_fraction",
        "warn_above": 0.30,
        "message": "fraction of all tags not assigned to any annotated feature "
        "(intergenic / off-annotation)",
    },
]


# Germline karyotypic-sex plausibility (capability C3 follow-on,
# germline-sex-check-plausibility). Infers karyotypic sex from X-heterozygosity
# (+ Y presence) over a germline VCF, WARN-capped like the other plausibility
# packs. Uncalibrated engineering defaults, NOT a clinical or diagnostic claim;
# never over-reads a VCF-only signal into a confident call (see
# sex_plausibility.py's UNVERIFIED-when-uncomputable branch).
#   X_HET_LOW: at/below this X-het ratio reads XY (mostly hemizygous X calls).
#   X_HET_HIGH: at/above this X-het ratio reads XX (autosomal-level X het).
#   Between the two bands is implausible for either karyotype -> discordant/WARN.
#   MIN_X_SITES: fewer callable (non-PAR) X sites than this -> indeterminate/
#       UNVERIFIED (too little signal to call).
#   Y_PRESENT_FLOOR: at/above this many non-PAR chrY variant sites -> Y is
#       considered present (strengthens/contradicts the X-het call).
X_HET_LOW = 0.10
X_HET_HIGH = 0.20
MIN_X_SITES = 20
Y_PRESENT_FLOOR = 5

# Deliberately no SEX_PLAUSIBILITY_PACK/_RULE_PACKS entry: the derived
# sex_plausibility call is bimodal (XY / XX / discordant / indeterminate),
# which a single warn_below/warn_above band cannot express, so
# sex_plausibility.py hand-builds its QCResults directly from the four
# scalar constants above rather than running them through evaluate().


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


def _expected_range(check: dict) -> str | None:
    """Human-readable bound description for the QCResult, honoring whichever bounds exist."""
    warn_below = check.get("warn_below")
    warn_above = check.get("warn_above")
    if warn_below is not None and warn_above is not None:
        return f"[{warn_below}, {warn_above}]"
    if warn_above is not None:
        return f"<= {warn_above}"
    if warn_below is not None:
        return f">= {warn_below}"
    return None


_BOUND_KEYS = ("fail_below", "fail_above", "warn_below", "warn_above")


def _is_band_less(check: dict) -> bool:
    """True if `check` declares none of the four bound keys.

    A rule with no bounds at all can only ever fall through `_status_for` to
    "pass" -- it asserts nothing, so `evaluate` marks it `informational=True`
    (verdict-neutral; see `overall_verdict`).

    Do NOT key this off `_expected_range(check) is None` instead -- that is a
    trap. `_expected_range` inspects ONLY warn_below/warn_above, so a rule
    with just `fail_below` (no warn_*) ALSO renders no expected_range, yet it
    very much CAN fail. Using `_expected_range` here would mark that rule
    informational too, making a can-fail rule unfalsifiable -- strictly worse
    than the bug this predicate fixes. Bound presence, checked directly
    against all four keys, is the only honest signal.
    """
    return not any(key in check for key in _BOUND_KEYS)


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
                    informational=_is_band_less(check),
                )
            )
    return results
