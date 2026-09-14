"""Injectable second-quantifier seam (PRD rnaseq-concordance-autorun, Phase 1).

Cross-tool count concordance (`count_concordance.py`) needs a second, independent
gene-count matrix on the same FASTQs. This seam lets Contig produce that second
matrix by running a second quantifier (kallisto by default) against an index,
then collapsing its transcript-level output to gene level. A turnkey run needs no
prebuilt kb-ref directory: `build_kallisto_index` builds the index in-seam, and
`t2g_from_gtf`/`write_t2g` derive the transcript->gene map from the annotation.

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

from pydantic import ValidationError

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

# The kallisto index file name, written under the index directory.
_INDEX_NAME = "index.idx"


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


def _run_kallisto_index(argv: list[str]) -> int:
    """Default index builder: run `kallisto index`; return its exit code.

    A nonzero exit carries the tool's stderr detail into a
    SecondQuantifierError. This subprocess success path is intentionally NEVER
    exercised in CI (kallisto is not installed there); tests inject a fake
    builder through `build_kallisto_index`.
    """
    result = subprocess.run(argv, capture_output=True)
    if result.returncode != 0:
        detail = result.stderr.decode(errors="replace").strip() if result.stderr else ""
        raise SecondQuantifierError(
            f"kallisto index exited nonzero ({result.returncode}): {detail}"
        )
    return result.returncode


def build_kallisto_index(
    transcriptome: str,
    index_dir: Path,
    builder: Callable[[list[str]], int] | None = None,
) -> Path:
    """Build a kallisto index for `transcriptome`; return the index dir.

    Validates the transcriptome FASTA exists BEFORE any spawn (a clear error
    beats a confusing tool failure), then runs
    `kallisto index -i <index_dir>/index.idx <transcriptome>` through the
    injectable `builder` (default `_run_kallisto_index`). A missing binary or a
    nonzero exit is folded into SecondQuantifierError.

    The default builder's subprocess success path is NEVER exercised in CI
    (kallisto is not installed there); CI injects a fake builder.
    """
    if not Path(transcriptome).is_file():
        raise SecondQuantifierError(f"transcriptome FASTA not found: {transcriptome}")

    index_path = Path(index_dir)
    argv = [_KALLISTO, "index", "-i", str(index_path / _INDEX_NAME), transcriptome]

    run = builder if builder is not None else _run_kallisto_index
    try:
        returncode = run(argv)
    except FileNotFoundError as exc:
        raise SecondQuantifierError(
            f"kallisto not found (is the '{_KALLISTO}' binary on PATH?): {exc}"
        ) from exc
    if returncode != 0:
        raise SecondQuantifierError(f"kallisto index exited nonzero ({returncode})")
    return index_path


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


def _parse_gtf_attributes(field: str) -> dict[str, str]:
    """Parse a GTF column-9 attribute string into a dict (pure).

    GTF attributes look like `gene_id "ENSG1"; transcript_id "ENST1";` (optionally
    with a `gene_name`). GFF3-style `ID=...;Parent=...` attributes do not match
    the `<key> <value>` grammar, so they yield no keys and the caller skips the
    line.
    """
    attrs: dict[str, str] = {}
    for chunk in field.split(";"):
        chunk = chunk.strip()
        if not chunk:
            continue
        key, _, value = chunk.partition(" ")
        if not value:
            continue
        attrs[key] = value.strip().strip('"')
    return attrs


def t2g_from_gtf(path: Path) -> tuple[dict[str, str], dict[str, str]]:
    """Derive a transcript->gene map (plus gene names) from a GTF (pure).

    Returns `(transcript_id -> gene_id, transcript_id -> gene_name)`. Only lines
    carrying BOTH `gene_id` and `transcript_id` attributes contribute: a `gene`
    line has no transcript to map, and a transcript line without a `gene_id`
    cannot be mapped at all, so both are skipped rather than guessed. `gene_name`
    is captured only when present (no fabricated names).
    """
    mapping: dict[str, str] = {}
    gene_names: dict[str, str] = {}
    with open(path, newline="") as fh:
        for line in fh:
            line = line.rstrip("\n")
            if not line or line.startswith("#"):
                continue
            fields = line.split("\t")
            if len(fields) < 9:
                continue
            attrs = _parse_gtf_attributes(fields[8])
            transcript_id = attrs.get("transcript_id")
            gene_id = attrs.get("gene_id")
            if not transcript_id or not gene_id:
                continue
            mapping[transcript_id] = gene_id
            gene_name = attrs.get("gene_name")
            if gene_name:
                gene_names[transcript_id] = gene_name
    return mapping, gene_names


def write_t2g(
    index_dir: Path, mapping: dict[str, str], gene_names: dict[str, str]
) -> Path:
    """Write `<index_dir>/t2g.txt`; return its path.

    Column contract (the shape `_parse_t2g` reads and the kb-ref convention
    uses): `transcript_id<TAB>gene_id`, with an optional third `gene_name` column
    only for transcripts that have a name. The directory must already exist (the
    index build creates it).
    """
    out_path = Path(index_dir) / _T2G_NAME
    with open(out_path, "w", newline="") as fh:
        for transcript_id, gene_id in mapping.items():
            gene_name = gene_names.get(transcript_id)
            if gene_name:
                fh.write(f"{transcript_id}\t{gene_id}\t{gene_name}\n")
            else:
                fh.write(f"{transcript_id}\t{gene_id}\n")
    return out_path


def run_kallisto_quantifier(reads: str, index: str, out_dir: str) -> str:
    """Run kallisto to produce a second gene-count matrix; return its path.

    Validates that the reads sample sheet and the index directory exist BEFORE
    any spawn (a clear error beats a confusing tool failure), derives FASTQ paths
    from the sample sheet, builds the `kallisto quant` command, runs it, parses
    the resulting `abundance.tsv`, collapses transcripts to genes via the index's
    `t2g.txt`, and writes `<out_dir>/second.gene_counts.tsv`.

    A missing binary (FileNotFoundError from the spawn), a nonzero exit, a
    malformed sample sheet (bare ValueError / pydantic ValidationError from
    `fastq_paths`), or a missing transcript->gene map is re-raised as a clear
    SecondQuantifierError, never leaked.

    The subprocess success path (steps 3-7 below) is intentionally NOT exercised
    in CI; the manual gate covers it against a real kallisto index and FASTQs.
    """
    reads_path = Path(reads)
    index_path = Path(index)
    if not reads_path.is_file():
        raise SecondQuantifierError(f"second quantifier reads sheet not found: {reads}")
    if not index_path.is_dir():
        raise SecondQuantifierError(f"second quantifier index not found: {index}")

    try:
        fastqs = [str(p) for p in fastq_paths(reads)]
    except (ValueError, ValidationError) as exc:
        raise SecondQuantifierError(
            f"second quantifier reads sheet is malformed: {reads} ({exc})"
        ) from exc
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
