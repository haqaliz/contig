"""Contig's CURATED pipeline registry.

We map an assay to an ALREADY-VALIDATED pipeline; we do NOT generate workflows
(that is Layer 1, which we consume, not build). `match_assay` is a deterministic,
rule-based intent provider — a replaceable component, not the moat.
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
]

_BY_ASSAY: dict[str, PipelineEntry] = {e.assay: e for e in REGISTRY}


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
}


def match_assay(goal: str) -> str | None:
    """Map a free-text goal to a registered assay key, or None if nothing matches.

    Case-insensitive substring matching — a deterministic, replaceable intent
    provider, not an LLM and not the moat.
    """
    text = goal.lower()
    for assay, keywords in _ASSAY_KEYWORDS.items():
        if any(kw in text for kw in keywords):
            return assay
    return None
