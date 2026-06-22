"""Infer the shape of a run's input from its sample sheet (ARCHITECTURE §P4).

A pre-flight read of the sample rows that the planner surfaces to the user
*before* a run starts: how many samples, paired/single/mixed layout, and the
warnings worth seeing up front (no replicates, single-end reads, mixed layouts).
"""

from __future__ import annotations

from contig.models import DataShape
from contig.samplesheet import SampleRow

# Assays whose analysis needs biological replicates, so a single sample is worth
# a warning. Bulk differential-expression RNA-seq does. Single-sample germline
# variant calling does not, and single-cell RNA-seq does not either: it measures
# many cells WITHIN a sample, so bulk replicates are not the relevant unit.
# methyl-seq, 16S amplicon (ampliseq), and shotgun metagenomics (mag) are also
# not bulk-replicate assays: each sample is analyzed on its own (per-sample
# methylation calls, per-sample ASV tables, per-sample assemblies/bins), so a
# single sample is valid and raises no replicate warning. They are absent from
# this set, and assay_expects_replicates returns False for them.
_REPLICATE_ASSAYS = {"rnaseq"}


def assay_expects_replicates(assay: str) -> bool:
    """Whether an assay's analysis expects biological replicates.

    scrnaseq and variant_calling return False (a single sample is valid); rnaseq
    returns True. This is the assay decision `inspect_data_shape` consumes via
    its `expects_replicates` flag.
    """
    return assay in _REPLICATE_ASSAYS


def inspect_data_shape(rows: list[SampleRow], expects_replicates: bool = True) -> DataShape:
    """Infer the run's input shape and surface up-front warnings.

    `expects_replicates` is an assay decision the caller makes: RNA-seq DE needs
    replicates, but single-sample germline variant calling is valid, so the
    "needs replicates" warning is suppressed when replicates aren't expected.
    """
    n_samples = len(rows)
    n_paired = sum(1 for r in rows if r.fastq_2 is not None)

    if n_paired == n_samples:
        layout = "paired"
    elif n_paired == 0:
        layout = "single"
    else:
        layout = "mixed"

    warnings: list[str] = []
    if expects_replicates and n_samples < 2:
        warnings.append(
            f"only {n_samples} sample(s); differential expression needs replicates"
        )
    if layout == "single":
        warnings.append("single-end reads detected")
    elif layout == "mixed":
        warnings.append("mixed paired-end and single-end layouts across samples")

    return DataShape(n_samples=n_samples, layout=layout, warnings=warnings)
