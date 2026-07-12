"""Deterministic RNA-seq cross-tool count-concordance metric (PRD C1, rnaseq slice).

Real files only, via pytest tmp_path; no mocks, no tool execution, no network.
"""

import gzip

import pytest

from contig.verification.count_concordance import (
    _MIN_SHARED_GENES,
    _spearman,
    concordance_results,
    count_concordance,
    evaluate_count_concordance,
    parse_count_matrix,
    results_from_counts,
    stats_from_counts,
)


def _write_matrix(path, lines):
    """lines: list of already-tab-joined row strings (no trailing newline)."""
    path.write_text("".join(line + "\n" for line in lines))
    return path


def _write_counts(path, mapping):
    """mapping: {gene_id: scalar count} -> a one-sample-column TSV, no header."""
    lines = [f"{gene}\t{value}" for gene, value in mapping.items()]
    return _write_matrix(path, lines)


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


# --- Phase 2: stats, results, and the assay gate -----------------------------


def _concordant_pair(tmp_path):
    """12 shared genes, identical counts -> rho 1.0, fraction 1.0."""
    mapping = {f"gene{i:02d}": (i + 1) * 100 for i in range(12)}
    a = _write_counts(tmp_path / "a.tsv", mapping)
    b = _write_counts(tmp_path / "b.tsv", dict(mapping))
    return a, b


def test_concordant_pair_passes(tmp_path):
    a, b = _concordant_pair(tmp_path)

    results = {r.check: r for r in concordance_results(a, b)}

    assert results["spearman_concordance"].status == "pass"
    assert results["spearman_concordance"].value == 1.0
    assert results["fraction_agreeing"].status == "pass"
    assert results["fraction_agreeing"].value == 1.0


def test_divergent_pair_warns(tmp_path):
    # Reversed rank assignment over 12 shared genes -> rho = -1.0 (< 0.90).
    a = _write_counts(
        tmp_path / "a.tsv", {f"gene{i:02d}": (i + 1) * 100 for i in range(12)}
    )
    b = _write_counts(
        tmp_path / "b.tsv", {f"gene{i:02d}": (12 - i) * 100 for i in range(12)}
    )

    results = {r.check: r for r in concordance_results(a, b)}
    spearman = results["spearman_concordance"]

    assert spearman.status == "warn"
    assert spearman.value is not None and spearman.value < 0.90
    assert str(spearman.value) in spearman.message  # metric named in the message


def test_few_shared_genes_unverified(tmp_path):
    # Only 5 shared genes (< _MIN_SHARED_GENES) -> WARN-capped checks UNVERIFIED.
    assert _MIN_SHARED_GENES == 10
    shared = {f"gene{i:02d}": (i + 1) * 100 for i in range(5)}
    a = _write_counts(tmp_path / "a.tsv", dict(shared))
    b = _write_counts(tmp_path / "b.tsv", dict(shared))

    results = {r.check: r for r in concordance_results(a, b)}

    assert results["spearman_concordance"].status == "unverified"
    assert results["spearman_concordance"].value is None
    assert results["fraction_agreeing"].status == "unverified"
    assert results["fraction_agreeing"].value is None
    # overlap is still meaningful and reported.
    assert results["gene_overlap"].status == "pass"
    assert results["gene_overlap"].value == 1.0


def test_no_shared_genes_unverified(tmp_path):
    a = _write_counts(tmp_path / "a.tsv", {f"a{i:02d}": i + 1 for i in range(12)})
    b = _write_counts(tmp_path / "b.tsv", {f"b{i:02d}": i + 1 for i in range(12)})

    results = {r.check: r for r in concordance_results(a, b)}

    assert results["spearman_concordance"].status == "unverified"
    assert results["spearman_concordance"].value is None
    assert results["fraction_agreeing"].status == "unverified"
    assert results["gene_overlap"].status == "pass"
    assert results["gene_overlap"].value == 0.0


def test_zero_count_genes_agree_no_crash(tmp_path):
    # A zero-count gene present in both -> agrees (|0-0|/max(0,0,1)=0), no crash.
    mapping = {f"gene{i:02d}": i * 100 for i in range(12)}  # gene00 == 0
    a = _write_counts(tmp_path / "a.tsv", dict(mapping))
    b = _write_counts(tmp_path / "b.tsv", dict(mapping))

    stats = count_concordance(a, b)

    assert stats.fraction_agreeing == 1.0
    assert stats.shared == 12


def test_tiny_counts_disagree(tmp_path):
    # 1 vs 2 -> |1-2|/max(1,2,1) = 0.5 > 0.10 -> disagrees, no crash.
    a = _write_counts(tmp_path / "a.tsv", {"geneA": 1})
    b = _write_counts(tmp_path / "b.tsv", {"geneA": 2})

    stats = count_concordance(a, b)

    assert stats.fraction_agreeing == 0.0


def test_gene_overlap_informational_never_warns(tmp_path):
    # Low overlap (subset annotation) but perfect correlation on shared genes:
    # gene_overlap must stay PASS (informational), spearman PASS.
    a_map = {f"gene{i:02d}": (i + 1) * 100 for i in range(20)}
    b_map = {f"gene{i:02d}": (i + 1) * 100 for i in range(12)}  # subset of a
    a = _write_counts(tmp_path / "a.tsv", a_map)
    b = _write_counts(tmp_path / "b.tsv", b_map)

    results = {r.check: r for r in concordance_results(a, b)}

    assert results["gene_overlap"].value < 0.90  # low overlap
    assert results["gene_overlap"].status == "pass"  # yet never WARN
    assert results["spearman_concordance"].status == "pass"


def test_results_tagged_kind_concordance(tmp_path):
    a, b = _concordant_pair(tmp_path)

    results = concordance_results(a, b)

    assert len(results) == 3
    assert all(r.kind == "concordance" for r in results)


def test_evaluate_gate_rnaseq(tmp_path):
    a, b = _concordant_pair(tmp_path)

    results = evaluate_count_concordance(a, b, assay="rnaseq")

    assert len(results) == 3
    assert {r.check for r in results} == {
        "spearman_concordance",
        "fraction_agreeing",
        "gene_overlap",
    }


def test_evaluate_gate_skips_non_rnaseq(tmp_path):
    a, b = _concordant_pair(tmp_path)

    assert evaluate_count_concordance(a, b, assay="variant_calling") == []


# --- Phase 1 (this slice): dict-based concordance seam ------------------------


def test_stats_from_counts_matches_path_wrapper(tmp_path):
    # The dict seam over pre-parsed counts equals count_concordance over the same
    # counts written to TSVs and parsed back.
    dict_a = {f"gene{i:02d}": float((i + 1) * 100) for i in range(12)}
    dict_b = {f"gene{i:02d}": float((i + 2) * 100) for i in range(12)}
    a = _write_counts(tmp_path / "a.tsv", dict_a)
    b = _write_counts(tmp_path / "b.tsv", dict_b)

    from_dicts = stats_from_counts(dict_a, dict_b)
    from_paths = count_concordance(a, b)

    assert from_dicts == from_paths


def test_results_from_counts_matches_path_wrapper(tmp_path):
    # results_from_counts over the dicts + display names returns three QCResults
    # identical (check, status, value, message) to concordance_results over files.
    dict_a = {f"gene{i:02d}": float((i + 1) * 100) for i in range(12)}
    dict_b = {f"gene{i:02d}": float((i + 2) * 100) for i in range(12)}
    a = _write_counts(tmp_path / "a.tsv", dict_a)
    b = _write_counts(tmp_path / "b.tsv", dict_b)

    from_dicts = results_from_counts(dict_a, dict_b, a.name, b.name)
    from_paths = concordance_results(a, b)

    assert len(from_dicts) == 3
    assert [
        (r.check, r.status, r.value, r.message) for r in from_dicts
    ] == [(r.check, r.status, r.value, r.message) for r in from_paths]
