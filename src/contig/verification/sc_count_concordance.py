"""Single-cell cross-tool count-concordance QC (PRD C1, scrnaseq slice).

The single-cell analog of `count_concordance.py`: it corroborates an scrnaseq run's
own count matrix against a second, independently produced matrix. A single-cell tool
(STARsolo, Cell Ranger, alevin-fry/simpleaf, kallisto|bustools) can pass every metric
and structural threshold yet disagree with another quantifier on the actual per-gene
signal — so a second matrix is a cheap, deterministic sanity check.

Because the shared concordance math is gene-level, we collapse a sparse cell x gene
MatrixMarket triplet into a per-gene **pseudobulk** total (sum across all cells) and
feed that into the unchanged core (`results_from_counts`). Cell-count and
cluster-stability concordance are deliberately deferred; `.h5ad` is deferred too
(stdlib-only, no HDF5/AnnData reader). This module reads pure `.mtx`/`.tsv`(.gz) text
with no third-party numerical libraries, no tool execution, and no network.

Same conservative posture as the RNA-seq path: concordance corroborates, it is NOT
ground truth, so the worst it can do to a verdict is WARN; an unparseable / ambiguous
matrix is surfaced as one explicit UNVERIFIED, never a silent pass.
"""

from __future__ import annotations

import os
from pathlib import Path

from contig.models import QCResult
from contig.verification.count_concordance import (
    _concordance,
    _open_text,
    parse_count_matrix,
    results_from_counts,
)


class ScMatrixError(Exception):
    """A single-cell matrix could not be parsed: missing sibling, unparseable, or
    an ambiguous gene/cell orientation. Callers turn this into one UNVERIFIED
    result rather than letting it become a false pass."""


# Assays for which single-cell count concordance is defined. Kept as a set so a
# future single-cell assay is a one-line addition.
_SC_CONCORDANCE_ASSAYS = {"scrnaseq"}

# Glob for a run's primary single-cell count matrix (STARsolo/Cell Ranger triplet).
# Exported so the CLI resolver (Phase 3) can select the matrix by pattern.
_SC_MATRIX_GLOB = "*matrix.mtx*"


def _resolve_sibling(mtx_dir: Path, stem: str) -> Path | None:
    """Find `<stem>.tsv` or `<stem>.tsv.gz` beside the matrix, preferring non-gz."""
    plain = mtx_dir / f"{stem}.tsv"
    if plain.exists():
        return plain
    gz = mtx_dir / f"{stem}.tsv.gz"
    if gz.exists():
        return gz
    return None


def load_mtx_pseudobulk(mtx_path: str | os.PathLike) -> dict[str, float]:
    """Collapse a 10x-style MatrixMarket triplet into {gene_id: pseudobulk total}.

    Resolves the sibling `features.tsv`(.gz) and `barcodes.tsv`(.gz) in the matrix's
    directory (preferring non-gz), infers the gene axis by matching the `.mtx`
    dimensions to the feature/barcode counts, and sums each gene's counts across all
    cells. Raises `ScMatrixError` on a missing sibling, an ambiguous/mismatched
    orientation, an out-of-range gene index, or zero usable genes.
    """
    mtx_path = Path(mtx_path)
    mtx_dir = mtx_path.parent

    features_path = _resolve_sibling(mtx_dir, "features")
    barcodes_path = _resolve_sibling(mtx_dir, "barcodes")
    if features_path is None or barcodes_path is None:
        raise ScMatrixError(
            f"features.tsv/barcodes.tsv not found beside {mtx_path.name}"
        )

    # features.tsv: column 1 is the gene id (10x id,name,type); a single-column
    # file yields the sole token. Blank lines skipped.
    with _open_text(features_path) as fh:
        features = [
            line.rstrip("\n").split("\t")[0] for line in fh if line.strip()
        ]

    # barcodes.tsv: one non-blank line per cell.
    with _open_text(barcodes_path) as fh:
        n_barcodes = sum(1 for line in fh if line.strip())

    with _open_text(mtx_path) as fh:
        lines = fh.readlines()

    # Skip the %%MatrixMarket banner and any %-comment / blank line; the first
    # remaining line is the dimension line `nrows ncols nnz`.
    idx = 0
    while idx < len(lines):
        stripped = lines[idx].strip()
        if not stripped or stripped.startswith("%"):
            idx += 1
            continue
        break
    if idx >= len(lines):
        raise ScMatrixError(f"{mtx_path.name} has no dimension line")

    dim_parts = lines[idx].split()
    if len(dim_parts) < 2:
        raise ScMatrixError(f"{mtx_path.name} has a malformed dimension line")
    try:
        nrows = int(dim_parts[0])
        ncols = int(dim_parts[1])
    except ValueError as exc:
        raise ScMatrixError(
            f"{mtx_path.name} has a non-integer dimension line"
        ) from exc

    n_features = len(features)
    genes_are_rows = nrows == n_features and ncols == n_barcodes
    genes_are_cols = nrows == n_barcodes and ncols == n_features
    if genes_are_rows and genes_are_cols:
        # Square (genes == cells): the axis is ambiguous, refuse to guess.
        raise ScMatrixError(
            f"cannot determine gene axis: mtx dims ({nrows},{ncols}) are square "
            f"vs features {n_features}, barcodes {n_barcodes}"
        )
    if genes_are_rows:
        gene_axis_is_row = True
    elif genes_are_cols:
        gene_axis_is_row = False
    else:
        raise ScMatrixError(
            f"cannot determine gene axis: mtx dims ({nrows},{ncols}) vs "
            f"features {n_features}, barcodes {n_barcodes}"
        )

    totals: dict[str, float] = {}
    saw_any = False
    for raw in lines[idx + 1:]:
        parts = raw.split()
        if len(parts) < 3:
            continue  # blank / short line
        r_str, c_str, val_str = parts[0], parts[1], parts[2]
        gene_1based = int(r_str) if gene_axis_is_row else int(c_str)
        gene_idx = gene_1based - 1
        if gene_idx < 0 or gene_idx >= n_features:
            raise ScMatrixError(
                f"{mtx_path.name}: gene index {gene_1based} out of range "
                f"(1..{n_features})"
            )
        gene_id = features[gene_idx]
        totals[gene_id] = totals.get(gene_id, 0.0) + float(val_str)
        saw_any = True

    if not saw_any:
        raise ScMatrixError(f"{mtx_path.name}: no usable gene counts found")

    return totals


def load_sc_matrix(path: str | os.PathLike) -> dict[str, float]:
    """Sniff-route a second matrix: a `.mtx`(.gz) triplet vs a dense pseudobulk TSV.

    A path whose name ends in `.mtx` or `.mtx.gz` goes through the MatrixMarket
    pseudobulk loader (siblings auto-resolved); anything else is treated as a dense
    gene-count TSV and parsed by the shared `parse_count_matrix`.
    """
    name = Path(path).name
    if name.endswith(".mtx") or name.endswith(".mtx.gz"):
        return load_mtx_pseudobulk(path)
    return parse_count_matrix(path)


def evaluate_sc_count_concordance(
    primary_mtx: str | os.PathLike,
    second: str | os.PathLike,
    assay: str,
    second_name: str | None = None,
) -> list[QCResult]:
    """Assay-gated single-cell concordance: pseudobulk both matrices, reuse the core.

    Returns `[]` for a non-scrnaseq assay. Otherwise loads the primary `.mtx` triplet
    and the (sniff-routed) second matrix into per-gene pseudobulk dicts and defers to
    the unchanged `results_from_counts`. If either matrix cannot be parsed
    (`ScMatrixError`/`OSError`/`ValueError`), returns exactly one explicit
    `sc_count_concordance` UNVERIFIED naming the offending file and reason — never a
    silent pass, never a crash.

    `second_name` overrides the display label for the second matrix. The user-supplied
    path leaves it `None` (labelled by basename, unchanged); the autorun passes the tool
    that produced it (e.g. `"STARsolo"`) so the corroboration line names the second tool
    instead of an opaque `matrix.mtx vs matrix.mtx`.
    """
    if assay not in _SC_CONCORDANCE_ASSAYS:
        return []

    label_b = second_name or Path(second).name

    try:
        a = load_mtx_pseudobulk(primary_mtx)
        b = load_sc_matrix(second)
    except (ScMatrixError, OSError, ValueError) as exc:
        return [
            _concordance(
                check="sc_count_concordance",
                status="unverified",
                message=(
                    f"single-cell matrix {Path(primary_mtx).name} / "
                    f"{label_b} located but could not be parsed "
                    f"({exc}); concordance UNVERIFIED, not a pass"
                ),
                value=None,
            )
        ]

    return results_from_counts(a, b, Path(primary_mtx).name, label_b)
