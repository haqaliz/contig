"""Citation-ready methods-section generator (PRD contract C).

`render_methods` templates a deterministic methods paragraph from a RunRecord: the
pipeline and revision, the assay it serves, the key parameters, the Nextflow and
container provenance, and the verdict plus QC summary. It is offline and rule
based (no LLM, no network), so the same bundle always renders the same prose a
researcher can paste into a manuscript.
"""

from __future__ import annotations

import os

from contig.models import RunRecord
from contig.registry import assay_for_pipeline
from contig.verification.annotation_surface import corroborated_by_line

# Human-readable assay labels for the prose. A pipeline whose assay is not in the
# curated registry simply renders without an assay clause (see render_methods).
_ASSAY_LABEL: dict[str, str] = {
    "rnaseq": "bulk RNA-seq",
    "scrnaseq": "single-cell RNA-seq",
    "variant_calling": "germline short-variant calling",
    "somatic_variant_calling": "somatic (tumor–normal) short-variant calling",
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


def _reference_clause(record: RunRecord) -> str:
    """A clause describing the reference genome used, if recorded; empty string otherwise."""
    ri = record.reference_identity
    if ri is None:
        return ""
    if ri.mode == "igenomes":
        key = ri.genome or "unknown"
        return (
            f" The analysis was run against the iGenomes {key} reference"
            " (downloaded by the pipeline)."
        )
    # explicit mode
    fasta_base = os.path.basename(ri.fasta) if ri.fasta else "unknown"
    gtf_base = os.path.basename(ri.gtf) if ri.gtf else "unknown"
    sha_snippet = ri.fasta_sha256[:12] if ri.fasta_sha256 else None
    if sha_snippet:
        return (
            f" The analysis was run against reference FASTA {fasta_base}"
            f" (sha256 {sha_snippet}...) and annotation {gtf_base}."
        )
    return (
        f" The analysis was run against reference FASTA {fasta_base}"
        f" and annotation {gtf_base}."
    )


def _annotation_clause(record: RunRecord) -> str:
    """A clause attributing the annotation tool(s) + DB version(s), if recorded.

    M4 enables both VEP and SnpEff on the variant assays, so a run may carry
    more than one provenance entry; each renders as "Tool version" joined by
    "; " (e.g. "VEP v110; SnpEff 5.1"). Defensive against a raw single-object
    shape (the pre-M4 legacy serialization) in case this field is ever read
    before the model validator has normalized it.
    """
    provenances = record.annotation_identity
    if provenances is None:
        return ""
    if not isinstance(provenances, list):
        provenances = [provenances]
    if not provenances:
        return ""
    def _one(ai: object) -> str:
        # "VEP v110 (cache/build 110_GRCh38)"; the cache/build parenthetical is
        # omitted entirely when db_version is absent (no orphan label). Labeled
        # "cache/build", never "database version" (it is the annotation cache
        # release, not a ClinVar/gnomAD version -- PRD D1/R2).
        base = f"{ai.tool}{f' {ai.version}' if ai.version else ''}"
        db_version = getattr(ai, "db_version", None)
        if db_version:
            return f"{base} (cache/build {db_version})"
        return base

    rendered = "; ".join(_one(ai) for ai in provenances)
    return (
        f" Variant annotation was performed with {rendered}; annotations are"
        " reported as produced by that tool and its databases (research use)."
    )


def _corroboration_clause(record: RunRecord) -> str:
    """The M4 cross-tool corroboration sentence, or '' when not computable.

    Sourced verbatim from the shared `corroborated_by_line` helper (which reads
    M4's already-computed concordance results and never recomputes); it already
    names the annotators, so it is appended as a self-contained sentence right
    after the annotation clause. `None` -> omitted entirely (PRD D2).
    """
    line = corroborated_by_line(record)
    if line is None:
        return ""
    return " " + line


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
    # Prefer the explicit assay carried on the record (it disambiguates assays
    # that share a pipeline, e.g. somatic vs germline nf-core/sarek); fall back
    # to the legacy pipeline-derived lookup for records without an assay.
    assay = record.assay or assay_for_pipeline(record.pipeline)
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
        + _reference_clause(record)
        + _annotation_clause(record)
        + _corroboration_clause(record)
        + _provenance_clause(record)
        + _qc_clause(record)
    )
    return paragraph
