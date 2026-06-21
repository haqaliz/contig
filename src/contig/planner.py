"""The planning / intake layer (ARCHITECTURE §P4).

Map a free-text goal + the data shape to a CURATED pipeline and propose params,
producing a human-readable Plan the user approves before running. The NL→assay
step is a deterministic, replaceable provider (contig.registry.match_assay); the
moat is the curated registry + the run/verify engine, not the prompting. Contig
does not author workflows; it selects validated ones.
"""

from __future__ import annotations

from os import PathLike

from contig.datashape import inspect_data_shape
from contig.models import Plan
from contig.registry import match_assay, select_pipeline
from contig.samplesheet import parse_samplesheet


class PlanningError(ValueError):
    """Raised when no curated plan can be proposed for the given goal."""


# Assays whose analysis requires biological replicates (so a single sample is a
# warning). Differential-expression RNA-seq does; germline variant calling does not.
_REPLICATE_ASSAYS = {"rnaseq"}


def plan(
    goal: str,
    samplesheet_path: str | PathLike[str],
    reference_params: dict[str, object] | None = None,
) -> Plan:
    """Propose an analysis Plan from a goal + sample sheet for the user to approve."""
    assay = match_assay(goal)
    if assay is None:
        raise PlanningError(
            f"could not infer a supported assay from the goal: {goal!r} "
            "(Contig currently curates: RNA-seq)"
        )
    entry = select_pipeline(assay)
    # Replicates are an RNA-seq DE requirement; single-sample germline calling is fine.
    shape = inspect_data_shape(
        parse_samplesheet(samplesheet_path), expects_replicates=(assay in _REPLICATE_ASSAYS)
    )

    params: dict[str, object] = {"input": str(samplesheet_path), **(reference_params or {})}
    warnings = list(shape.warnings)
    if not reference_params:
        warnings.append("no reference specified; pass --genome or --fasta/--gtf to run")

    rationale = (
        f"Goal {goal!r} → assay '{assay}' → {entry.pipeline}@{entry.revision}; "
        f"{shape.n_samples} sample(s), {shape.layout}-end."
    )
    return Plan(
        assay=assay,
        pipeline=entry.pipeline,
        revision=entry.revision,
        params=params,
        rationale=rationale,
        warnings=warnings,
    )
