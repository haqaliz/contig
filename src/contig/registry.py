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
    PipelineEntry(
        assay="variant_calling",
        pipeline="nf-core/sarek",
        revision="3.5.1",
        description="Germline short-variant calling (GATK best-practices), research use.",
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
# inflected "differentially expressed". Order is irrelevant; first hit wins.
_ASSAY_KEYWORDS: dict[str, tuple[str, ...]] = {
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
    "variant_calling": (
        "variant calling",
        "germline variant",
        "call variants",
        "snp",
        "snv",
        "indel",
        "variant caller",
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
