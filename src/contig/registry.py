"""Contig's CURATED pipeline registry.

We map an assay to an ALREADY-VALIDATED pipeline; we do NOT generate workflows
(that is Layer 1, which we consume, not build). `match_assay` is a deterministic,
rule-based intent provider, a replaceable component, not the moat.
"""

from __future__ import annotations

from contig.models import PipelineEntry

REGISTRY: list[PipelineEntry] = [
    PipelineEntry(
        assay="rnaseq",
        pipeline="nf-core/rnaseq",
        revision="3.26.0",
        description="Bulk RNA-seq quantification + QC (differential-expression inputs).",
    ),
    # Somatic shares nf-core/sarek with germline. It is listed BEFORE the germline
    # variant_calling entry so that `_ASSAY_BY_PIPELINE` (last write wins) keeps
    # mapping "nf-core/sarek" -> "variant_calling": germline stays the legacy
    # reverse-lookup fallback, while the run path selects somatic via an explicit
    # assay override.
    PipelineEntry(
        assay="somatic_variant_calling",
        pipeline="nf-core/sarek",
        revision="3.5.1",
        description="Somatic tumor–normal short-variant calling (nf-core/sarek), research use.",
    ),
    PipelineEntry(
        assay="variant_calling",
        pipeline="nf-core/sarek",
        revision="3.5.1",
        description="Germline short-variant calling (GATK best-practices), research use.",
    ),
    PipelineEntry(
        assay="scrnaseq",
        pipeline="nf-core/scrnaseq",
        # 4.1.0 is the latest released nf-core/scrnaseq tag (2024-10-30).
        revision="4.1.0",
        description="Single-cell RNA-seq quantification + per-cell QC (10x, DropSeq, SmartSeq).",
    ),
    PipelineEntry(
        assay="methylseq",
        pipeline="nf-core/methylseq",
        # 4.2.0 is the latest released nf-core/methylseq tag (2025-12-12).
        revision="4.2.0",
        description="Bisulfite sequencing methylation calling + QC (Bismark/bwa-meth).",
    ),
    PipelineEntry(
        assay="ampliseq",
        pipeline="nf-core/ampliseq",
        # 2.18.0 is the latest released nf-core/ampliseq tag (2026-06-17).
        revision="2.18.0",
        description="16S/ITS amplicon profiling: DADA2 denoising, ASV inference, taxonomy.",
    ),
    PipelineEntry(
        assay="mag",
        pipeline="nf-core/mag",
        # 5.4.2 is the latest released nf-core/mag tag (2026-03-31).
        revision="5.4.2",
        description="Shotgun metagenomics: assembly, binning, and bin QC (de novo MAGs).",
    ),
]

_BY_ASSAY: dict[str, PipelineEntry] = {e.assay: e for e in REGISTRY}
_ASSAY_BY_PIPELINE: dict[str, str] = {e.pipeline: e.assay for e in REGISTRY}


class UnknownAssayError(KeyError):
    """Raised when an assay has no curated pipeline in the registry."""


def select_pipeline(assay: str) -> PipelineEntry:
    """Return the curated pipeline entry for an assay.

    Raises UnknownAssayError (a KeyError) if the assay isn't registered.
    """
    try:
        return _BY_ASSAY[assay]
    except KeyError:
        raise UnknownAssayError(f"no curated pipeline for assay {assay!r}") from None


def assay_for_pipeline(pipeline: str) -> str | None:
    """Reverse lookup: the assay a registered pipeline serves, or None if unknown.

    The inverse of `select_pipeline`'s data: given e.g. "nf-core/sarek", return
    "variant_calling". Lets a caller route a known pipeline back to its assay
    (e.g. to pick the right verification rule pack).
    """
    return _ASSAY_BY_PIPELINE.get(pipeline)


# Deterministic keyword rules: free-text goal -> assay key. Lower-cased substring
# match. "differential" (not "differential expression") so it also catches the
# inflected "differentially expressed". First hit wins, so the MORE SPECIFIC
# assay is listed first: "scrna-seq" contains the substring "rna-seq", so
# scrnaseq must be checked before rnaseq or single-cell goals would be misrouted.
_ASSAY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "scrnaseq": (
        "single cell",
        "single-cell",
        "scrna-seq",
        "scrnaseq",
        "scrna",
        "10x",
    ),
    "rnaseq": (
        "rna-seq",
        "rnaseq",
        "rna seq",
        "differential expression",
        "differentially express",
        "gene expression",
        "transcript",
        "deg",
    ),
    # somatic tumor/normal calling is listed BEFORE variant_calling in iteration
    # order because "somatic variant calling" also contains the generic
    # "variant calling" needle; first-hit-wins means the more specific somatic
    # assay must be checked first (mirrors the scrnaseq-before-rnaseq ordering).
    # Germline needles do not contain any of these tumor/somatic tokens, so
    # germline goals are unaffected.
    "somatic_variant_calling": (
        "somatic",
        "tumor",
        "tumour",
        "tumor-normal",
        "tumor normal",
        "tumour-normal",
    ),
    "variant_calling": (
        "variant calling",
        "germline variant",
        "call variants",
        "snp",
        "snv",
        "indel",
        "variant caller",
    ),
    # methyl-seq before the others is harmless (no shared substrings), but kept
    # grouped with the new assays for readability.
    "methylseq": (
        "methylation",
        "methyl-seq",
        "methylseq",
        "bisulfite",
        "wgbs",
    ),
    # shotgun metagenomics. "metagenom" covers metagenome/metagenomic/metagenomics.
    # "mag"/"mags" are the recovered-genome synonym; we anchor them as standalone
    # tokens (leading space or "mags") so a bare "mag" inside e.g. "image" or
    # "magnitude" does not misroute. ampliseq is listed BEFORE mag so a goal that
    # names both a microbiome AND shotgun lands by the more specific amplicon
    # signal only when amplicon/16s/dada2 is present (see ampliseq keywords).
    "mag": (
        "metagenom",
        "shotgun",
        " mag",
        "mags",
    ),
    # 16S/ITS amplicon microbiome profiling. Listed AFTER mag in iteration order
    # does not matter here because these needles ("16s", "amplicon", "dada2") do
    # not appear in metagenomics goals; "microbiome" can co-occur with shotgun
    # work, but a microbiome goal without shotgun/metagenom routes to amplicon.
    "ampliseq": (
        "16s",
        "amplicon",
        "microbiome",
        "dada2",
    ),
}


def match_assay(goal: str) -> str | None:
    """Map a free-text goal to a registered assay key, or None if nothing matches.

    Case-insensitive substring matching, a deterministic, replaceable intent
    provider, not an LLM and not the moat.
    """
    text = goal.lower()
    for assay, keywords in _ASSAY_KEYWORDS.items():
        if any(kw in text for kw in keywords):
            return assay
    return None
