"""Deterministic RNA-seq cross-tool count-concordance metric (PRD C1, rnaseq slice).

Real files only, via pytest tmp_path; no mocks, no tool execution, no network.
"""

import gzip

import pytest

from contig.verification.count_concordance import (
    _spearman,
    parse_count_matrix,
)


def _write_matrix(path, lines):
    """lines: list of already-tab-joined row strings (no trailing newline)."""
    path.write_text("".join(line + "\n" for line in lines))
    return path


# --- Phase 1: parser ---------------------------------------------------------


def test_parse_sums_across_samples(tmp_path):
    m = _write_matrix(tmp_path / "counts.tsv", ["geneA\t10\t20", "geneB\t1\t2"])

    assert parse_count_matrix(m) == {"geneA": 30.0, "geneB": 3.0}


def test_parse_skips_header_row(tmp_path):
    m = _write_matrix(
        tmp_path / "counts.tsv",
        ["gene_id\tgene_name\tsample1", "geneA\tAlpha\t10"],
    )

    parsed = parse_count_matrix(m)
    assert "gene_id" not in parsed  # header is not a phantom gene
    assert parsed == {"geneA": 10.0}


def test_parse_skips_gene_name_column(tmp_path):
    # A non-numeric second column (Salmon's gene_name) is ignored; only the
    # numeric columns are summed.
    m = _write_matrix(tmp_path / "counts.tsv", ["geneA\tAlpha\t10\t20"])

    assert parse_count_matrix(m) == {"geneA": 30.0}


def test_parse_duplicate_gene_ids_sum(tmp_path):
    m = _write_matrix(tmp_path / "counts.tsv", ["geneA\t10", "geneA\t5"])

    assert parse_count_matrix(m) == {"geneA": 15.0}  # accumulate, not last-wins


def test_parse_gzip(tmp_path):
    rows = ["geneA\t10\t20", "geneB\t1\t2"]
    plain = _write_matrix(tmp_path / "counts.tsv", rows)
    gz = tmp_path / "counts.tsv.gz"
    with gzip.open(gz, "wt") as fh:
        fh.write("".join(line + "\n" for line in rows))

    assert parse_count_matrix(gz) == parse_count_matrix(plain)


def test_parse_unparseable_value_skipped(tmp_path):
    # A junk numeric cell is skipped, not fatal; a row with a numeric column
    # still yields that gene, a fully non-numeric row is dropped.
    m = _write_matrix(
        tmp_path / "counts.tsv",
        ["geneA\tNA\t10", "junkrow\tNA\tfoo"],
    )

    parsed = parse_count_matrix(m)
    assert parsed == {"geneA": 10.0}
    assert "junkrow" not in parsed


# --- Phase 1: Spearman -------------------------------------------------------


def test_spearman_monotonic_is_1():
    assert _spearman([1, 2, 3, 4], [10, 20, 30, 40]) == 1.0


def test_spearman_reversed_is_minus_1():
    assert _spearman([1, 2, 3, 4], [40, 30, 20, 10]) == -1.0


def test_spearman_ties_average_rank():
    # xs ranks (average-rank ties): [1.5, 1.5, 3, 4]; ys ranks: [1, 2, 3, 4].
    # Pearson of those ranks = 4.5 / sqrt(4.5 * 5.0) = sqrt(0.9) = 0.948683...
    rho = _spearman([1, 1, 2, 3], [1, 2, 3, 4])
    assert rho == pytest.approx(0.9486832980505, abs=1e-9)


def test_spearman_too_few_points_is_none():
    assert _spearman([1], [2]) is None


def test_spearman_constant_vector_is_none():
    # Zero variance in a rank vector -> correlation undefined -> None.
    assert _spearman([5, 5, 5], [1, 2, 3]) is None
