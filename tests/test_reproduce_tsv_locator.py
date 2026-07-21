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
        {"a": "1", "b": "2"},
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
