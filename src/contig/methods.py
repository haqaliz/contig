"""Citation-ready methods-section generator (PRD contract C).

`render_methods` templates a deterministic methods paragraph from a RunRecord: the
pipeline and revision, the assay it serves, the key parameters, the Nextflow and
container provenance, and the verdict plus QC summary. It is offline and rule
based (no LLM, no network), so the same bundle always renders the same prose a
researcher can paste into a manuscript.
"""

from __future__ import annotations

from contig.models import RunRecord
from contig.registry import assay_for_pipeline

# Human-readable assay labels for the prose. A pipeline whose assay is not in the
# curated registry simply renders without an assay clause (see render_methods).
_ASSAY_LABEL: dict[str, str] = {
    "rnaseq": "bulk RNA-seq",
    "scrnaseq": "single-cell RNA-seq",
    "variant_calling": "germline short-variant calling",
    "methylseq": "bisulfite methylation",
    "ampliseq": "16S/ITS amplicon",
    "mag": "shotgun metagenomics",
}


def _params_clause(record: RunRecord) -> str:
    """A deterministic, comma-joined rendering of the recorded parameters, or ''."""
    items = sorted(record.parameters.items())
    if not items:
        return ""
    rendered = ", ".join(f"{k}={v}" for k, v in items)
    return f" Key parameters: {rendered}."


def _provenance_clause(record: RunRecord) -> str:
    """The Nextflow version and container digests that pin the run, if recorded."""
    parts: list[str] = []
    if record.nextflow_version:
        parts.append(f"Nextflow {record.nextflow_version}")
    if record.container_digests:
        digests = ", ".join(
            f"{name} ({digest})"
            for name, digest in sorted(record.container_digests.items())
        )
        parts.append(f"pinned containers {digests}")
    if not parts:
        return ""
    return " Execution was pinned to " + " and ".join(parts) + "."


def _qc_clause(record: RunRecord) -> str:
    """A summary of the QC checks behind the verdict, or the unverified note."""
    verdict = record.verdict
    if not record.qc_results:
        return (
            f" The run verdict was {verdict}: no quality-control check covered this "
            "run, so the result is not claimed as verified."
        )
    checks = ", ".join(
        f"{qc.check} ({qc.status})" for qc in record.qc_results
    )
    return (
        f" The run verdict was {verdict}, supported by the following "
        f"quality-control checks: {checks}."
    )


def render_methods(record: RunRecord) -> str:
    """Render a citation-ready methods paragraph for a finished run.

    The wording is fixed and derived only from the record, so two runs with the
    same provenance produce the same paragraph (a stable, auditable artifact).
    """
    assay = assay_for_pipeline(record.pipeline)
    label = _ASSAY_LABEL.get(assay) if assay else None

    if label:
        opening = (
            f"{label.capitalize()} analysis was performed with the "
            f"{record.pipeline} pipeline (revision {record.pipeline_revision})."
        )
    else:
        opening = (
            f"Analysis was performed with the {record.pipeline} pipeline "
            f"(revision {record.pipeline_revision})."
        )

    paragraph = (
        opening
        + _params_clause(record)
        + _provenance_clause(record)
        + _qc_clause(record)
    )
    return paragraph
