"""Injectable second-quantifier seam (PRD rnaseq-concordance-autorun, Phase 1).

Cross-tool count concordance (`count_concordance.py`) needs a second, independent
gene-count matrix on the same FASTQs. This seam lets Contig produce that second
matrix by running a second quantifier (kallisto by default) against a prebuilt
index, then collapsing its transcript-level output to gene level.

The seam mirrors `VariantCaller`/`run_bcftools_caller` in `second_caller.py`: a
`CountQuantifier` is an injectable callable so the rest of the engine (and its
tests) never has to run a real tool. `kallisto_command` is a pure argv builder,
asserted directly in tests; `run_kallisto_quantifier` is the default
implementation that shells out. kallisto itself is never executed in CI (the
subprocess success path is covered only by a manual gate); tests exercise the
builder and the honest error paths.

`collapse_to_gene` is the scientific substance and is a PURE function: it is unit
tested for real, in CI, independent of kallisto ever running.

Honesty: a missing binary, missing reads, or a missing index raises a clear, named
`SecondQuantifierError`. It never leaks a bare FileNotFoundError, and a missing
transcript->gene map never silently degrades into a transcript-level matrix.
"""

from __future__ import annotations

import csv
import subprocess
from pathlib import Path
from typing import Callable, Iterable

from contig.samplesheet import fastq_paths

# A second quantifier: (reads, index, out_dir) -> produced gene-matrix path. The
# CLI auto path takes one of these and tests inject a fake, exactly as
# `VariantCaller` is injected in second_caller.py, so no tool runs in CI.
CountQuantifier = Callable[[str, str, str], str]

# The binary name, as a module-level constant so tests can monkeypatch it to a
# bogus value and drive the missing-binary error path without touching PATH.
_KALLISTO = "kallisto"

# Name of the produced second gene-count matrix, written under out_dir.
_SECOND_MATRIX_NAME = "second.gene_counts.tsv"

# kallisto quant's transcript-level abundance output, read from out_dir.
_ABUNDANCE_NAME = "abundance.tsv"

# The transcript->gene map file name, resolved under the index directory (the
# kb-ref convention: a kallisto index directory carries its own t2g.txt alongside
# the index file).
_T2G_NAME = "t2g.txt"


class SecondQuantifierError(Exception):
    """Raised when the second quantifier cannot run or its inputs are missing.

    A missing binary, missing/unreadable reads or index, a nonzero exit, or a
    missing transcript->gene map are all surfaced through this one named error so
    the CLI can turn them into a clear skip note (no false PASS, no leaked
    traceback, and never a silent transcript-level matrix masquerading as gene
    counts).
    """


def kallisto_command(fastqs: list[str], index: str, out_dir: str) -> list[str]:
    """Build the `kallisto quant` argv as a single list (pure).

    `kallisto quant -i <index> -o <out_dir> <fastq...>`. No execution, no I/O.
    """
    return [_KALLISTO, "quant", "-i", index, "-o", out_dir, *fastqs]


def tx2gene_path(index: str) -> Path:
    """Resolve the transcript->gene map path anchored under the index dir.

    kb-ref convention: `<index>/t2g.txt`. Anchoring the collapse input to the
    index dir (rather than accepting a free-floating path) means the mapping used
    to produce gene counts is always explicit and never silently dropped.
    """
    return Path(index) / _T2G_NAME


def collapse_to_gene(
    rows: Iterable[tuple[str, float]], t2g: dict[str, str]
) -> dict[str, float]:
    """Sum transcript-level `est_counts` up to gene level (pure).

    `rows` is an iterable of `(transcript_id, est_counts)` pairs (as read from
    kallisto's `abundance.tsv`); `t2g` maps transcript_id -> gene_id. Transcripts
    that sum to the same gene are added together. A transcript absent from `t2g`
    is dropped from the result — documented behavior, not a silent bug: an
    unannotated transcript cannot be attributed to any gene, so it cannot
    contribute to a gene-level count.
    """
    genes: dict[str, float] = {}
    for transcript_id, est_counts in rows:
        gene_id = t2g.get(transcript_id)
        if gene_id is None:
            continue
        genes[gene_id] = genes.get(gene_id, 0.0) + est_counts
    return genes


def _parse_abundance(path: Path) -> list[tuple[str, float]]:
    """Parse kallisto's `abundance.tsv` into `(target_id, est_counts)` rows.

    Columns: target_id, length, eff_length, est_counts, tpm. The header row is
    skipped.
    """
    rows: list[tuple[str, float]] = []
    with open(path, newline="") as fh:
        reader = csv.reader(fh, delimiter="\t")
        next(reader, None)  # header
        for record in reader:
            if not record:
                continue
            target_id, _length, _eff_length, est_counts, *_rest = record
            rows.append((target_id, float(est_counts)))
    return rows


def _parse_t2g(path: Path) -> dict[str, str]:
    """Parse a transcript<TAB>gene_id[...] map into `{transcript_id: gene_id}`."""
    mapping: dict[str, str] = {}
    with open(path, newline="") as fh:
        for line in fh:
            line = line.rstrip("\n")
            if not line:
                continue
            fields = line.split("\t")
            if len(fields) < 2:
                continue
            mapping[fields[0]] = fields[1]
    return mapping


def run_kallisto_quantifier(reads: str, index: str, out_dir: str) -> str:
    """Run kallisto to produce a second gene-count matrix; return its path.

    Validates that the reads sample sheet and the index directory exist BEFORE
    any spawn (a clear error beats a confusing tool failure), derives FASTQ paths
    from the sample sheet, builds the `kallisto quant` command, runs it, parses
    the resulting `abundance.tsv`, collapses transcripts to genes via the index's
    `t2g.txt`, and writes `<out_dir>/second.gene_counts.tsv`.

    A missing binary (FileNotFoundError from the spawn), a nonzero exit, or a
    missing transcript->gene map is re-raised as a clear SecondQuantifierError,
    never leaked.

    The subprocess success path (steps 3-7 below) is intentionally NOT exercised
    in CI; the manual gate covers it against a real kallisto index and FASTQs.
    """
    reads_path = Path(reads)
    index_path = Path(index)
    if not reads_path.is_file():
        raise SecondQuantifierError(f"second quantifier reads sheet not found: {reads}")
    if not index_path.is_dir():
        raise SecondQuantifierError(f"second quantifier index not found: {index}")

    fastqs = [str(p) for p in fastq_paths(reads)]
    if not fastqs:
        raise SecondQuantifierError(f"second quantifier reads sheet has no FASTQs: {reads}")
    missing = [f for f in fastqs if not Path(f).is_file()]
    if missing:
        raise SecondQuantifierError(
            f"second quantifier FASTQ(s) not found: {', '.join(missing)}"
        )

    argv = kallisto_command(fastqs, index, out_dir)

    try:
        result = subprocess.run(argv, capture_output=True)
    except FileNotFoundError as exc:
        raise SecondQuantifierError(
            f"kallisto not found (is the '{_KALLISTO}' binary on PATH?): {exc}"
        ) from exc

    if result.returncode != 0:
        detail = result.stderr.decode(errors="replace").strip() if result.stderr else ""
        raise SecondQuantifierError(
            f"kallisto exited nonzero ({result.returncode}): {detail}"
        )

    abundance = Path(out_dir) / _ABUNDANCE_NAME
    if not abundance.is_file():
        raise SecondQuantifierError(f"kallisto abundance output not found: {abundance}")
    rows = _parse_abundance(abundance)

    t2g_file = tx2gene_path(index)
    if not t2g_file.is_file():
        raise SecondQuantifierError(
            f"transcript->gene map not found (never emitting a transcript-level "
            f"matrix silently): {t2g_file}"
        )
    t2g = _parse_t2g(t2g_file)

    genes = collapse_to_gene(rows, t2g)

    out_path = Path(out_dir) / _SECOND_MATRIX_NAME
    with open(out_path, "w") as fh:
        for gene_id, count in genes.items():
            fh.write(f"{gene_id}\t{count}\n")

    return str(out_path)
