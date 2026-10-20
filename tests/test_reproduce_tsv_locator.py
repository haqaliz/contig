"""Boundary tests for C8 slice 3 phase 2: the pure TSV/CSV cell resolver
`resolve_cell` and the gzip-transparent table reader `_read_table`.

Strict TDD: this file is written before `resolve_cell`/`_read_table` exist in
src/contig/verification/reproduce.py.

Mirrors tests/test_reproduce_locator.py's structure (the JSON pure-walker
tests): `resolve_cell` must never raise -- any unresolved, ambiguous, or
malformed input returns `(None, reason)`. `_read_table` must never raise --
any I/O, decode, or parse error returns `None`.
"""

from __future__ import annotations

import gzip

from contig.verification.reproduce import _read_table, resolve_cell

# ---------------------------------------------------------------------------
# resolve_cell -- header mode, happy paths
# ---------------------------------------------------------------------------

_HEADER_ROWS = [
    ["gene_id", "log2FoldChange", "padj"],
    ["ENSG1", "-2.31", "0.001"],
    ["ENSG2", "0.5", "0.2"],
]


def test_resolve_cell_header_column_by_name_hit():
    cell, reason = resolve_cell(_HEADER_ROWS, "log2FoldChange", 0, True)
    assert cell == "-2.31"
    assert reason == ""


def test_resolve_cell_header_column_by_int_hit():
    cell, reason = resolve_cell(_HEADER_ROWS, 1, 0, True)
    assert cell == "-2.31"
    assert reason == ""


def test_resolve_cell_header_row_by_index_hit():
    cell, reason = resolve_cell(_HEADER_ROWS, "padj", 1, True)
    assert cell == "0.2"
    assert reason == ""


def test_resolve_cell_header_row_by_key_single_match():
    cell, reason = resolve_cell(_HEADER_ROWS, "log2FoldChange", {"gene_id": "ENSG2"}, True)
    assert cell == "0.5"
    assert reason == ""


# ---------------------------------------------------------------------------
# resolve_cell -- header mode, failure paths (always UNVERIFIED, never raise)
# ---------------------------------------------------------------------------


def test_resolve_cell_row_key_zero_matches_returns_none_with_count():
    cell, reason = resolve_cell(_HEADER_ROWS, "log2FoldChange", {"gene_id": "NOPE"}, True)
    assert cell is None
    assert "0 rows" in reason


def test_resolve_cell_row_key_multiple_matches_returns_none_with_count():
    rows = [
        ["gene_id", "val"],
        ["ENSG1", "1"],
        ["ENSG1", "2"],
    ]
    cell, reason = resolve_cell(rows, "val", {"gene_id": "ENSG1"}, True)
    assert cell is None
    assert "2 rows" in reason


def test_resolve_cell_column_name_absent_returns_none():
    cell, reason = resolve_cell(_HEADER_ROWS, "not_a_column", 0, True)
    assert cell is None
    assert reason


def test_resolve_cell_duplicate_header_name_returns_none():
    rows = [
        ["gene_id", "gene_id", "padj"],
        ["ENSG1", "ENSG1dup", "0.001"],
    ]
    cell, reason = resolve_cell(rows, "gene_id", 0, True)
    assert cell is None
    assert reason


def test_resolve_cell_column_int_out_of_range_returns_none():
    cell, reason = resolve_cell(_HEADER_ROWS, 99, 0, True)
    assert cell is None
    assert reason


def test_resolve_cell_row_int_out_of_range_returns_none_names_data_row_count():
    cell, reason = resolve_cell(_HEADER_ROWS, "padj", 99, True)
    assert cell is None
    assert "2" in reason  # 2 data rows


def test_resolve_cell_ragged_row_shorter_than_column_returns_none():
    rows = [
        ["gene_id", "log2FoldChange", "padj"],
        ["ENSG1", "-2.31"],  # missing the padj cell
    ]
    cell, reason = resolve_cell(rows, "padj", 0, True)
    assert cell is None
    assert reason


def test_resolve_cell_empty_rows_returns_none():
    cell, reason = resolve_cell([], "padj", 0, True)
    assert cell is None
    assert reason


def test_resolve_cell_header_only_zero_data_rows_returns_none():
    rows = [["gene_id", "padj"]]
    cell, reason = resolve_cell(rows, "padj", 0, True)
    assert cell is None
    assert reason


# ---------------------------------------------------------------------------
# resolve_cell -- headerless mode
# ---------------------------------------------------------------------------

_HEADERLESS_ROWS = [
    ["a1", "a2", "a3"],
    ["b1", "b2", "b3"],
]


def test_resolve_cell_headerless_int_hit():
    cell, reason = resolve_cell(_HEADERLESS_ROWS, 1, 0, False)
    assert cell == "a2"
    assert reason == ""


def test_resolve_cell_headerless_row_out_of_range_returns_none():
    cell, reason = resolve_cell(_HEADERLESS_ROWS, 0, 99, False)
    assert cell is None
    assert reason


def test_resolve_cell_headerless_column_out_of_range_returns_none():
    cell, reason = resolve_cell(_HEADERLESS_ROWS, 99, 0, False)
    assert cell is None
    assert reason


# ---------------------------------------------------------------------------
# resolve_cell -- key compare is exact on the .strip()ed cell
# ---------------------------------------------------------------------------


def test_resolve_cell_key_match_strips_trailing_space_in_cell():
    rows = [
        ["id", "val"],
        ["  x  ", "10"],
    ]
    cell, reason = resolve_cell(rows, "val", {"id": "x"}, True)
    assert cell == "10"
    assert reason == ""


def test_resolve_cell_key_match_different_string_does_not_match():
    rows = [
        ["id", "val"],
        ["y", "10"],
    ]
    cell, reason = resolve_cell(rows, "val", {"id": "x"}, True)
    assert cell is None
    assert "0 rows" in reason


# ---------------------------------------------------------------------------
# resolve_cell -- multi-key AND row matching [table-locator-predicates]
# ---------------------------------------------------------------------------

_MULTI_KEY_ROWS = [
    ["gene", "condition", "log2FoldChange"],
    ["TP53", "treated", "-2.31"],
    ["TP53", "control", "0.5"],
    ["BRCA1", "treated", "1.2"],
]


def test_resolve_cell_multi_key_row_matches_when_all_predicates_hold():
    cell, reason = resolve_cell(
        _MULTI_KEY_ROWS, "log2FoldChange", {"gene": "TP53", "condition": "treated"}, True
    )
    assert cell == "-2.31"
    assert reason == ""


def test_resolve_cell_multi_key_row_zero_matches_returns_none_with_count():
    cell, reason = resolve_cell(
        _MULTI_KEY_ROWS, "log2FoldChange", {"gene": "TP53", "condition": "nope"}, True
    )
    assert cell is None
    assert "0 rows" in reason


def test_resolve_cell_multi_key_row_two_matches_returns_none_with_count():
    rows = [
        ["gene", "condition", "log2FoldChange"],
        ["TP53", "treated", "-2.31"],
        ["TP53", "treated", "0.5"],
    ]
    cell, reason = resolve_cell(
        rows, "log2FoldChange", {"gene": "TP53", "condition": "treated"}, True
    )
    assert cell is None
    assert "2 rows" in reason


def test_resolve_cell_multi_key_absent_key_column_returns_none_naming_column():
    cell, reason = resolve_cell(
        _MULTI_KEY_ROWS, "log2FoldChange", {"gene": "TP53", "sample": "S1"}, True
    )
    assert cell is None
    assert "sample" in reason
    assert "not found in header" in reason


def test_resolve_cell_multi_key_duplicate_header_among_key_columns_returns_none():
    rows = [
        ["gene", "gene", "log2FoldChange"],
        ["TP53", "BRCA1", "-2.31"],
    ]
    cell, reason = resolve_cell(
        rows, "log2FoldChange", {"gene": "TP53", "condition": "treated"}, True
    )
    assert cell is None
    assert "gene" in reason
    assert "ambiguous" in reason


def test_resolve_cell_multi_key_ragged_row_short_of_key_column_is_unresolved():
    rows = [
        ["gene", "condition", "log2FoldChange"],
        ["TP53"],  # ragged: shorter than the header
    ]
    cell, reason = resolve_cell(
        rows, "log2FoldChange", {"gene": "TP53", "condition": "treated"}, True
    )
    assert cell is None
    assert "0 rows" in reason


def test_resolve_cell_multi_key_strips_key_cells_and_values():
    rows = [
        ["gene", "condition", "log2FoldChange"],
        [" TP53 ", "  treated", "-2.31"],
    ]
    cell, reason = resolve_cell(
        rows, "log2FoldChange", {"gene": "TP53", "condition": "treated"}, True
    )
    assert cell == "-2.31"
    assert reason == ""


# ---------------------------------------------------------------------------
# resolve_cell -- regex and numeric row predicates [C8-1]
# ---------------------------------------------------------------------------

_PREDICATE_ROWS = [
    ["gene", "padj"],
    ["TP53", "0.05"],
    ["BRCA1", "0.5"],
    ["tp53-mut", "NA"],
]


def test_resolve_cell_row_regex_predicate_matches():
    cell, reason = resolve_cell(_PREDICATE_ROWS, "padj", {"gene": {"regex": "^BRC"}}, True)
    assert cell == "0.5"
    assert reason == ""


def test_resolve_cell_row_regex_predicate_honours_inline_flags():
    cell, reason = resolve_cell(
        _PREDICATE_ROWS, "padj", {"gene": {"regex": "(?i)^tp53$"}}, True
    )
    assert cell == "0.05"
    assert reason == ""


def test_resolve_cell_row_regex_predicate_strips_the_cell():
    rows = [["gene", "padj"], ["  TP53  ", "0.05"]]
    cell, reason = resolve_cell(rows, "padj", {"gene": {"regex": "^TP53$"}}, True)
    assert cell == "0.05"
    assert reason == ""


def test_resolve_cell_row_regex_predicate_zero_matches_returns_none_with_count():
    cell, reason = resolve_cell(_PREDICATE_ROWS, "padj", {"gene": {"regex": "^NOPE"}}, True)
    assert cell is None
    assert "0 rows" in reason


def test_resolve_cell_row_regex_predicate_two_matches_returns_none_with_count():
    rows = [["gene", "padj"], ["TP53a", "0.05"], ["TP53b", "0.5"]]
    cell, reason = resolve_cell(rows, "padj", {"gene": {"regex": "^TP53"}}, True)
    assert cell is None
    assert "2 rows" in reason


def test_resolve_cell_row_numeric_gte_bound_is_inclusive():
    cell, reason = resolve_cell(_PREDICATE_ROWS, "padj", {"padj": {"gte": 0.05}}, True)
    assert cell is None  # 0.05 and 0.5 both match -> ambiguous
    assert "2 rows" in reason

    rows = [["gene", "padj"], ["A", "0.05"], ["B", "NA"]]
    cell, reason = resolve_cell(rows, "padj", {"padj": {"gte": 0.05}}, True)
    assert cell == "0.05"
    assert reason == ""


def test_resolve_cell_row_numeric_lt_bound_is_exclusive():
    rows = [["gene", "padj"], ["A", "0.05"]]
    cell, reason = resolve_cell(rows, "padj", {"padj": {"lt": 0.05}}, True)
    assert cell is None
    assert "0 rows" in reason


def test_resolve_cell_row_numeric_range_selects_one_row():
    cell, reason = resolve_cell(
        _PREDICATE_ROWS, "gene", {"padj": {"gt": 0.1, "lte": 0.5}}, True
    )
    assert cell == "BRCA1"
    assert reason == ""


def test_resolve_cell_row_numeric_eq_composes_with_a_comparison():
    rows = [["gene", "padj"], ["A", "0.5"], ["B", "0.5001"]]
    cell, reason = resolve_cell(
        rows, "gene", {"padj": {"gte": 0.5, "eq": 0.5}}, True
    )
    assert cell == "A"
    assert reason == ""


def test_resolve_cell_row_numeric_unparseable_cell_is_not_a_match():
    cell, reason = resolve_cell(_PREDICATE_ROWS, "gene", {"padj": {"lt": 1}}, True)
    assert cell is None  # 0.05 and 0.5 match; "NA" is simply skipped
    assert "2 rows" in reason


def test_resolve_cell_row_numeric_does_not_accept_a_percent_suffix():
    rows = [["gene", "padj"], ["A", "5%"]]
    cell, reason = resolve_cell(rows, "gene", {"padj": {"gt": 0}}, True)
    assert cell is None
    assert "0 rows" in reason


def test_resolve_cell_row_predicates_and_with_exact_strings():
    cell, reason = resolve_cell(
        _PREDICATE_ROWS,
        "gene",
        {"gene": "TP53", "padj": {"lte": 0.1}},
        True,
    )
    assert cell == "TP53"
    assert reason == ""


def test_resolve_cell_row_predicate_malformed_is_unresolved_never_raises():
    malformed = [
        {},
        {"regex": "("},
        {"regex": 5},
        {"gt": "1"},
        {"gt": 1, "regex": "x"},
        {"nope": 1},
    ]
    for predicate in malformed:
        cell, reason = resolve_cell(
            _PREDICATE_ROWS, "gene", {"padj": predicate}, True
        )
        assert cell is None
        assert reason
        assert "predicate" in reason


# ---------------------------------------------------------------------------
# resolve_cell -- never raises, wild/adversarial inputs
# ---------------------------------------------------------------------------


def test_resolve_cell_never_raises_on_wild_inputs():
    rows = [
        ["gene_id", "log2FoldChange"],
        ["ENSG1", "-2.31"],
        ["ENSG2"],  # ragged: shorter than the header
    ]
    wild_columns = ["log2FoldChange", "missing", 0, 1, 99, -1, 2.5, None, True, ""]
    wild_rows = [
        0,
        1,
        99,
        -1,
        {"gene_id": "ENSG1"},
        {"missing": "x"},
        {},
        {"gene_id": 5},
        {5: "x"},
        None,
        [1, 2],
        "row",
    ]
    for header in (True, False):
        for column in wild_columns:
            for row in wild_rows:
                result = resolve_cell(rows, column, row, header)
                assert isinstance(result, tuple)
                assert len(result) == 2
                cell, reason = result
                assert cell is None or isinstance(cell, str)
                assert isinstance(reason, str)

    # A well-formed multi-key row object is a VALID shape -- never raises,
    # returns a (str | None, str) tuple whether its keys resolve or not (the
    # fixture lacks the "a"/"b" columns, so that one lands on a named reason).
    for row in ({"a": "1", "b": "2"}, {"gene_id": "ENSG1", "log2FoldChange": "-2.31"}):
        result = resolve_cell(rows, "log2FoldChange", row, True)
        assert isinstance(result, tuple)
        assert len(result) == 2
        cell, reason = result
        assert cell is None or isinstance(cell, str)
        assert isinstance(reason, str)

    degenerate_shapes = [[], [[]], [["a"]], [["a", "b"], []]]
    for shape in degenerate_shapes:
        for column in (0, "a", -1, 999):
            for row in (0, {"a": "1"}, -1, 999):
                for header in (True, False):
                    result = resolve_cell(shape, column, row, header)
                    assert isinstance(result, tuple)
                    assert len(result) == 2


# ---------------------------------------------------------------------------
# _read_table
# ---------------------------------------------------------------------------


def test_read_table_reads_tsv(tmp_path):
    path = tmp_path / "data.tsv"
    path.write_text("gene_id\tval\nENSG1\t-2.31\n", encoding="utf-8")
    rows = _read_table(path, "\t")
    assert rows == [["gene_id", "val"], ["ENSG1", "-2.31"]]


def test_read_table_reads_csv(tmp_path):
    path = tmp_path / "data.csv"
    path.write_text("gene_id,val\nENSG1,-2.31\n", encoding="utf-8")
    rows = _read_table(path, ",")
    assert rows == [["gene_id", "val"], ["ENSG1", "-2.31"]]


def test_read_table_reads_gzip_tsv(tmp_path):
    path = tmp_path / "data.tsv.gz"
    with gzip.open(path, "wt", encoding="utf-8", newline="") as f:
        f.write("gene_id\tval\nENSG1\t-2.31\n")
    rows = _read_table(path, "\t")
    assert rows == [["gene_id", "val"], ["ENSG1", "-2.31"]]


def test_read_table_directory_path_returns_none(tmp_path):
    directory = tmp_path / "a_directory"
    directory.mkdir()
    assert _read_table(directory, "\t") is None


def test_read_table_non_utf8_returns_none(tmp_path):
    path = tmp_path / "bad.tsv"
    path.write_bytes(b"gene_id\tval\n\xff\xfe\x00\x01\n")
    assert _read_table(path, "\t") is None


def test_read_table_missing_file_returns_none(tmp_path):
    path = tmp_path / "does_not_exist.tsv"
    assert _read_table(path, "\t") is None


def test_read_table_truncated_gzip_returns_none(tmp_path):
    # A real gzip stream truncated mid-body raises EOFError from stdlib
    # gzip, not OSError -- must still degrade to None, never raise.
    path = tmp_path / "truncated.tsv.gz"
    with gzip.open(path, "wt", encoding="utf-8", newline="") as f:
        f.write("gene_id\tval\nENSG1\t-2.31\nENSG2\t0.5\nENSG3\t1.2\n")
    full_bytes = path.read_bytes()
    path.write_bytes(full_bytes[: len(full_bytes) // 2])
    assert _read_table(path, "\t") is None


def test_read_table_corrupt_gzip_body_returns_none(tmp_path):
    # A valid gzip header followed by garbage raises zlib.error, not
    # OSError -- must still degrade to None, never raise.
    path = tmp_path / "corrupt.tsv.gz"
    path.write_bytes(b"\x1f\x8b\x08\x00" + b"\x00" * 20)
    assert _read_table(path, "\t") is None
