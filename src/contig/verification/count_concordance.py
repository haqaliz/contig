"""Cross-tool RNA-seq quantification-concordance QC (ARCHITECTURE §6; PRD C1, rnaseq).

A second, independent quantifier on the same reads is a standard way to sanity-check
a count matrix: a tool-specific systematic error (wrong index, annotation drift,
aligner bias) can pass every metric and structural threshold yet disagree with
another quantifier. This module measures that agreement deterministically over two
provided gene-count matrices, with no tool execution and no network.

It is the count-matrix analog of the germline `concordance.py`: same conservative
posture (concordance corroborates, it is NOT ground truth, so the worst it can do to
a verdict is WARN, never FAIL), same UNVERIFIED-on-no-signal honesty, same
`kind="concordance"` tag so the dashboard groups it apart from the metric and
structural checks. Genes are compared on the shared gene-id set; per gene we compare
the summed count across all sample columns.

Thresholds (0.90) and the agreement tolerance (10%) are uncalibrated engineering
defaults, tunable like the rule packs, absorbed by the UNVERIFIED-when-too-few-genes
guarantee. Not clinical claims.
"""

from __future__ import annotations

import gzip
import os
from dataclasses import dataclass
from pathlib import Path

from contig.models import QCResult

# Documented engineering defaults (tunable), NOT clinical claims. Below these we
# WARN; there is no FAIL band in this slice.
_SPEARMAN_WARN_BELOW = 0.90
_FRACTION_AGREEING_WARN_BELOW = 0.90

# A gene "agrees" when |a - b| / max(a, b, 1) <= this. The max(a, b, 1) denominator
# makes two all-zero genes agree (diff 0), never divides by zero, and damps tiny
# counts (1 vs 2 -> 0.5, correctly disagreeing).
_AGREEMENT_REL_TOL = 0.10

# Below this many shared genes, a Spearman/fraction is meaningless (2 genes could
# report rho=1.0 -> a false PASS), so the two WARN-capped checks are UNVERIFIED.
# Uncalibrated default, code-overridable.
_MIN_SHARED_GENES = 10

# Assays for which cross-tool count concordance is defined. Only RNA-seq quantifies
# genes; kept as a set so a new assay (e.g. single-cell) is a one-line addition.
_COUNT_CONCORDANCE_ASSAYS = {"rnaseq"}

# Glob for the run's primary gene-count matrix (nf-core/rnaseq Salmon merge).
# Exported so the CLI resolver can select the matrix by pattern.
_COUNT_MATRIX_GLOB = "*salmon.merged.gene_counts*"


def _concordance(
    check: str,
    status: str,
    message: str,
    value: float | None = None,
    expected_range: str | None = None,
) -> QCResult:
    """Build a QCResult tagged as concordance so the dashboard groups it correctly."""
    return QCResult(
        check=check,
        status=status,
        message=message,
        value=value,
        expected_range=expected_range,
        kind="concordance",
    )


def _open_text(path: str | os.PathLike):
    """Open a matrix for text reading, transparently gunzipping a `.gz` path."""
    p = Path(path)
    if p.name.endswith(".gz"):
        return gzip.open(p, "rt")
    return open(p)


def parse_count_matrix(path: str | os.PathLike) -> dict[str, float]:
    """Parse a gene-count matrix into {gene_id: summed count across numeric columns}.

    Tolerant and gzip-transparent (mirrors the VCF parser style). The first column is
    the gene id; every remaining column that parses as a float is summed into that
    gene's scalar. A non-numeric column (e.g. Salmon's `gene_name`) is skipped. A row
    with NO parseable numeric column is skipped entirely — this is exactly how the
    header row (`gene_id  gene_name  sample1 …`) is dropped without a special sniff,
    so it never becomes a phantom gene. A repeated gene id ACCUMULATES (sum), never
    last-wins.
    """
    counts: dict[str, float] = {}
    with _open_text(path) as fh:
        for line in fh:
            line = line.rstrip("\n")
            if not line:
                continue
            cols = line.split("\t")
            if len(cols) < 2:
                continue
            gene_id = cols[0]
            total = 0.0
            saw_numeric = False
            for cell in cols[1:]:
                try:
                    total += float(cell)
                except ValueError:
                    continue
                saw_numeric = True
            if not saw_numeric:
                continue  # header / label-only row -> not a gene
            counts[gene_id] = counts.get(gene_id, 0.0) + total
    return counts


def _rank(values: list[float]) -> list[float]:
    """Average (fractional) ranks, 1-based, so tied values share their mean rank."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    n = len(values)
    while i < n:
        j = i
        while j + 1 < n and values[order[j + 1]] == values[order[i]]:
            j += 1
        # positions i..j (0-based) are tied -> average of 1-based ranks (i+1 .. j+1)
        avg = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    """Pearson correlation; None when either vector has zero variance."""
    n = len(xs)
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    dx = [x - mean_x for x in xs]
    dy = [y - mean_y for y in ys]
    cov = sum(a * b for a, b in zip(dx, dy))
    var_x = sum(a * a for a in dx)
    var_y = sum(b * b for b in dy)
    if var_x == 0 or var_y == 0:
        return None
    return cov / (var_x**0.5 * var_y**0.5)


def _spearman(xs: list[float], ys: list[float]) -> float | None:
    """Hand-rolled Spearman rho: average-rank tie handling, then Pearson of the ranks.

    Returns None when there are fewer than 2 points, or when either ranked vector has
    zero variance (a constant column -> correlation undefined). No scipy/numpy.
    """
    if len(xs) != len(ys):
        raise ValueError("xs and ys must be the same length")
    if len(xs) < 2:
        return None
    rho = _pearson(_rank(xs), _rank(ys))
    if rho is None:
        return None
    # Scrub IEEE dust so perfectly (anti-)correlated ranks land on exactly +/-1.0.
    return round(rho, 12)
