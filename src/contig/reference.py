"""Resolve an nf-core/rnaseq reference-genome specification.

A reference is given ONE of two mutually-exclusive ways:

- ``genome``: an iGenomes key (e.g. ``"GRCh38"``) that nf-core resolves and
  downloads itself — no local files required.
- ``fasta`` + ``gtf``: explicit local paths to a reference FASTA and its GTF
  annotation.

``resolve_reference`` validates the spec and returns the matching nf-core
params, raising :class:`ReferenceError` on anything invalid.
"""

from pathlib import Path


class ReferenceError(ValueError):
    """Raised when a reference-genome specification is invalid."""


def resolve_reference(genome=None, fasta=None, gtf=None):
    if genome is not None:
        if fasta is not None or gtf is not None:
            raise ReferenceError(
                "specify either --genome or --fasta/--gtf, not both"
            )
        return {"genome": genome}
    if fasta is None and gtf is None:
        raise ReferenceError(
            "a reference is required: --genome or --fasta/--gtf"
        )
    if fasta is None or gtf is None:
        raise ReferenceError(
            "explicit mode requires both --fasta and --gtf"
        )
    for label, path in (("--fasta", fasta), ("--gtf", gtf)):
        if not Path(path).exists():
            raise ReferenceError(f"{label} file not found: {path}")
    # Absolutize: Nextflow runs with cwd=run_dir, so a relative path handed to
    # nf-core would fail its "file does not exist" validation.
    return {"fasta": str(Path(fasta).resolve()), "gtf": str(Path(gtf).resolve())}
