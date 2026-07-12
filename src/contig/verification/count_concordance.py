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


def _agrees(a: float, b: float) -> bool:
    """A gene agrees when |a - b| / max(a, b, 1) <= _AGREEMENT_REL_TOL.

    The max(a, b, 1) denominator makes two all-zero genes agree (diff 0), never
    divides by zero, and damps tiny counts (1 vs 2 -> 0.5, correctly disagreeing).
    """
    return abs(a - b) / max(a, b, 1) <= _AGREEMENT_REL_TOL


@dataclass(frozen=True)
class CountConcordanceStats:
    """The deterministic outcome of comparing two count matrices.

    - shared: number of gene ids present in both matrices.
    - rho: Spearman rank correlation over the shared genes, or None when it could
      not be computed (< 2 shared genes or a constant count vector).
    - fraction_agreeing: fraction of shared genes within the relative tolerance, or
      None when there are no shared genes.
    - overlap: |A∩B| / |A∪B| of gene ids, 0.0 when the union is empty.
    """

    shared: int
    rho: float | None
    fraction_agreeing: float | None
    overlap: float


def stats_from_counts(
    a: dict[str, float], b: dict[str, float]
) -> CountConcordanceStats:
    """Compare two already-parsed count dicts over their shared genes.

    The pure-dict seam under `count_concordance`: takes pre-parsed {gene_id: count}
    maps so a non-TSV source (e.g. a single-cell pseudobulk) can feed the identical,
    deterministic concordance math without a file round-trip.
    """
    keys_a = set(a)
    keys_b = set(b)
    shared_keys = keys_a & keys_b
    union_keys = keys_a | keys_b

    overlap = (len(shared_keys) / len(union_keys)) if union_keys else 0.0

    # Sort so the paired vectors (and thus rho) are order-deterministic.
    shared = sorted(shared_keys)
    xs = [a[g] for g in shared]
    ys = [b[g] for g in shared]

    rho = _spearman(xs, ys) if shared else None

    if shared:
        agreeing = sum(1 for x, y in zip(xs, ys) if _agrees(x, y))
        fraction_agreeing: float | None = agreeing / len(shared)
    else:
        fraction_agreeing = None

    return CountConcordanceStats(
        shared=len(shared_keys),
        rho=rho,
        fraction_agreeing=fraction_agreeing,
        overlap=overlap,
    )


def count_concordance(
    matrix_a: str | os.PathLike, matrix_b: str | os.PathLike
) -> CountConcordanceStats:
    """Compare two count matrices over their shared genes; deterministic, reads only."""
    return stats_from_counts(parse_count_matrix(matrix_a), parse_count_matrix(matrix_b))


def concordance_results(
    matrix_a: str | os.PathLike, matrix_b: str | os.PathLike
) -> list[QCResult]:
    """Emit the three count-concordance checks for a pair of matrices.

    `spearman_concordance` and `fraction_agreeing` are WARN-capped (PASS at/above
    0.90, WARN below), but UNVERIFIED (value=None) when fewer than
    `_MIN_SHARED_GENES` genes are comparable — a correlation over 1-2 genes is
    meaningless and could report a false PASS, so we must not claim one. `rho` can
    also be None (a constant count vector), which is UNVERIFIED too. `gene_overlap`
    is informational and ALWAYS PASS — a second matrix built on a subset annotation
    legitimately overlaps poorly, so overlap must not cry wolf; the real signal lives
    in the other two. All results carry kind "concordance". Messages name both
    matrices by basename so the comparison is auditable.
    """
    return results_from_counts(
        parse_count_matrix(matrix_a),
        parse_count_matrix(matrix_b),
        Path(matrix_a).name,
        Path(matrix_b).name,
    )


def results_from_counts(
    a: dict[str, float],
    b: dict[str, float],
    name_a: str,
    name_b: str,
) -> list[QCResult]:
    """Emit the three count-concordance checks for two already-parsed count dicts.

    The pure-dict seam under `concordance_results`: same WARN-cap / UNVERIFIED-on-
    too-few-genes / informational-overlap contract, but keyed off pre-parsed maps and
    caller-supplied display names so a non-TSV source can reuse the identical checks.
    """
    stats = stats_from_counts(a, b)

    too_few = stats.shared < _MIN_SHARED_GENES

    # spearman_concordance
    if too_few or stats.rho is None:
        spearman_result = _concordance(
            "spearman_concordance",
            "unverified",
            f"{name_a} and {name_b} share {stats.shared} comparable gene(s) "
            f"(< {_MIN_SHARED_GENES} needed); too few to corroborate quantification "
            "(concordance is not ground truth)",
            value=None,
            expected_range=f">= {_SPEARMAN_WARN_BELOW}",
        )
    else:
        rho = round(stats.rho, 4)
        status = "warn" if stats.rho < _SPEARMAN_WARN_BELOW else "pass"
        spearman_result = _concordance(
            "spearman_concordance",
            status,
            f"{name_a} vs {name_b}: per-gene rank correlation {rho} over "
            f"{stats.shared} shared gene(s)",
            value=rho,
            expected_range=f">= {_SPEARMAN_WARN_BELOW}",
        )

    # fraction_agreeing
    if too_few or stats.fraction_agreeing is None:
        fraction_result = _concordance(
            "fraction_agreeing",
            "unverified",
            f"{name_a} and {name_b} share {stats.shared} comparable gene(s) "
            f"(< {_MIN_SHARED_GENES} needed); too few to corroborate quantification",
            value=None,
            expected_range=f">= {_FRACTION_AGREEING_WARN_BELOW}",
        )
    else:
        fraction = round(stats.fraction_agreeing, 4)
        status = (
            "warn" if stats.fraction_agreeing < _FRACTION_AGREEING_WARN_BELOW else "pass"
        )
        fraction_result = _concordance(
            "fraction_agreeing",
            status,
            f"{name_a} vs {name_b}: {fraction} of {stats.shared} shared gene(s) agree "
            f"within {int(_AGREEMENT_REL_TOL * 100)}% relative tolerance",
            value=fraction,
            expected_range=f">= {_FRACTION_AGREEING_WARN_BELOW}",
        )

    # gene_overlap (informational, never WARN)
    overlap = round(stats.overlap, 4)
    overlap_result = _concordance(
        "gene_overlap",
        "pass",
        f"{name_a} vs {name_b}: {stats.shared} shared gene(s); gene-id overlap "
        f"{overlap} (informational context, not a verdict lever)",
        value=overlap,
        expected_range=None,
    )

    return [spearman_result, fraction_result, overlap_result]


def evaluate_count_concordance(
    primary: str | os.PathLike,
    second: str | os.PathLike,
    assay: str,
) -> list[QCResult]:
    """Assay-gated entry point: count concordance where the assay quantifies genes.

    Returns the three `concordance_results` for an assay in
    `_COUNT_CONCORDANCE_ASSAYS` (RNA-seq today), else an empty list. Gating here keeps
    the caller (run_qc) from having to know which assays support count concordance.
    """
    if assay not in _COUNT_CONCORDANCE_ASSAYS:
        return []
    return concordance_results(primary, second)
