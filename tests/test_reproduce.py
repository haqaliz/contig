"""Boundary tests for C8 slice 1 phase 2: claims loader, tolerance classifier,
and the reproduce run engine.

Strict TDD: this file is written before any of load_claims/classify/run_reproduction
exist in src/contig/verification/reproduce.py.
"""

from __future__ import annotations

import gzip
import json
import math
import os
from pathlib import Path

import pytest

from contig.verification import reproduce as reproduce_module
from contig.verification.reproduce import (
    Claim,
    ClaimsError,
    Locator,
    NotebookLocator,
    PatternLocator,
    TableLocator,
    classify,
    load_claims,
    run_reproduction,
)

# A fixed synthetic run-start so freshness is decided purely by the mtimes we
# set with os.utime, never by wall-clock time.
_RUN_START = 1_000_000.0


# ---------------------------------------------------------------------------
# classify()
# ---------------------------------------------------------------------------


def test_classify_exact_match_is_reproduced():
    status, delta, message = classify(claimed=0.9, observed=0.9, tolerance=0.02)
    assert status == "reproduced"
    assert delta == 0.0
    assert message


def test_classify_within_band_but_not_exact_is_within_tolerance():
    status, delta, message = classify(claimed=1.0, observed=1.05, tolerance=0.1)
    assert status == "within_tolerance"
    assert delta == pytest.approx(0.05)
    assert message


def test_classify_outside_band_is_diverged_and_message_names_values():
    status, delta, message = classify(claimed=1.0, observed=1.5, tolerance=0.1)
    assert status == "diverged"
    assert delta == pytest.approx(0.5)
    assert "1.5" in message
    assert "1.0" in message
    assert "0.5" in message


def test_classify_observed_none_is_unverified():
    status, delta, message = classify(claimed=1.0, observed=None, tolerance=0.1)
    assert status == "unverified"
    assert delta is None
    assert message


def test_classify_nan_observed_is_unverified_never_diverged():
    status, delta, message = classify(claimed=1.0, observed=float("nan"), tolerance=0.1)
    assert status == "unverified"
    assert delta is None


def test_classify_inf_observed_is_unverified_never_diverged():
    status, delta, message = classify(claimed=1.0, observed=float("inf"), tolerance=0.1)
    assert status == "unverified"
    assert delta is None


def test_classify_nan_claimed_is_unverified():
    status, delta, message = classify(claimed=float("nan"), observed=1.0, tolerance=0.1)
    assert status == "unverified"
    assert delta is None


def test_classify_zero_claim_and_zero_observed_is_reproduced():
    status, delta, message = classify(claimed=0.0, observed=0.0, tolerance=0.1)
    assert status == "reproduced"
    assert delta == 0.0


def test_classify_zero_claim_and_nonzero_observed_is_diverged_absolute_fallback():
    # Documented case: _relative_delta falls back to abs(observed) when the
    # claimed (reference) value is 0.
    status, delta, message = classify(claimed=0.0, observed=5.0, tolerance=0.1)
    assert status == "diverged"
    assert delta == pytest.approx(5.0)


# ---------------------------------------------------------------------------
# load_claims()
# ---------------------------------------------------------------------------


def _write(tmp_path: Path, name: str, content: str) -> Path:
    p = tmp_path / name
    p.write_text(content)
    return p


def test_load_claims_happy_path(tmp_path):
    path = _write(
        tmp_path,
        "claims.json",
        json.dumps(
            [
                {"id": "auc", "value": 0.9, "tolerance": 0.05},
                {"id": "accuracy", "value": 0.8},
            ]
        ),
    )
    claims = load_claims(path)
    assert len(claims) == 2
    assert claims[0].id == "auc"
    assert claims[0].value == 0.9
    assert claims[0].tolerance == 0.05
    # default tolerance
    assert claims[1].id == "accuracy"
    assert claims[1].tolerance == 0.1


def test_load_claims_rejects_malformed_json(tmp_path):
    path = _write(tmp_path, "claims.json", "{not valid json")
    with pytest.raises(ClaimsError):
        load_claims(path)


def test_load_claims_rejects_non_list_top_level(tmp_path):
    path = _write(tmp_path, "claims.json", json.dumps({"id": "auc", "value": 0.9}))
    with pytest.raises(ClaimsError):
        load_claims(path)


def test_load_claims_rejects_item_missing_id(tmp_path):
    path = _write(tmp_path, "claims.json", json.dumps([{"value": 0.9}]))
    with pytest.raises(ClaimsError):
        load_claims(path)


def test_load_claims_rejects_item_missing_value(tmp_path):
    path = _write(tmp_path, "claims.json", json.dumps([{"id": "auc"}]))
    with pytest.raises(ClaimsError):
        load_claims(path)


def test_load_claims_rejects_non_numeric_value(tmp_path):
    path = _write(tmp_path, "claims.json", json.dumps([{"id": "auc", "value": "high"}]))
    with pytest.raises(ClaimsError):
        load_claims(path)


def test_load_claims_rejects_boolean_value(tmp_path):
    path = _write(tmp_path, "claims.json", json.dumps([{"id": "auc", "value": True}]))
    with pytest.raises(ClaimsError):
        load_claims(path)


def test_load_claims_rejects_duplicate_id(tmp_path):
    path = _write(
        tmp_path,
        "claims.json",
        json.dumps([{"id": "auc", "value": 0.9}, {"id": "auc", "value": 0.5}]),
    )
    with pytest.raises(ClaimsError):
        load_claims(path)


def test_load_claims_rejects_non_positive_tolerance(tmp_path):
    path = _write(
        tmp_path, "claims.json", json.dumps([{"id": "auc", "value": 0.9, "tolerance": 0}])
    )
    with pytest.raises(ClaimsError):
        load_claims(path)


def test_load_claims_rejects_non_numeric_string_tolerance(tmp_path):
    path = _write(
        tmp_path, "claims.json", json.dumps([{"id": "auc", "value": 0.9, "tolerance": "0.1"}])
    )
    with pytest.raises(ClaimsError):
        load_claims(path)


def test_load_claims_rejects_boolean_tolerance(tmp_path):
    path = _write(
        tmp_path, "claims.json", json.dumps([{"id": "auc", "value": 0.9, "tolerance": True}])
    )
    with pytest.raises(ClaimsError):
        load_claims(path)


# ---------------------------------------------------------------------------
# load_claims() -- output locator ("from" + "path") [C8 slice 1.5, Phase 2]
# ---------------------------------------------------------------------------


def test_load_claims_with_from_and_path_attaches_locator(tmp_path):
    path = _write(
        tmp_path,
        "claims.json",
        json.dumps([{"id": "auc", "value": 0.9, "from": "out/x.json", "path": "$.a"}]),
    )
    claims = load_claims(path)
    assert claims[0].locator == Locator("out/x.json", "$.a")


def test_load_claims_slice1_claim_has_no_locator(tmp_path):
    path = _write(tmp_path, "claims.json", json.dumps([{"id": "auc", "value": 0.9}]))
    claims = load_claims(path)
    assert claims[0].locator is None


def test_load_claims_rejects_from_without_path(tmp_path):
    path = _write(
        tmp_path,
        "claims.json",
        json.dumps([{"id": "auc", "value": 0.9, "from": "out/x.json"}]),
    )
    with pytest.raises(ClaimsError):
        load_claims(path)


def test_load_claims_rejects_path_without_from(tmp_path):
    path = _write(
        tmp_path,
        "claims.json",
        json.dumps([{"id": "auc", "value": 0.9, "path": "$.a"}]),
    )
    with pytest.raises(ClaimsError):
        load_claims(path)


def test_load_claims_rejects_non_string_from(tmp_path):
    path = _write(
        tmp_path,
        "claims.json",
        json.dumps([{"id": "auc", "value": 0.9, "from": 1, "path": "$.a"}]),
    )
    with pytest.raises(ClaimsError):
        load_claims(path)


def test_load_claims_rejects_non_string_path(tmp_path):
    path = _write(
        tmp_path,
        "claims.json",
        json.dumps([{"id": "auc", "value": 0.9, "from": "out/x.json", "path": 1}]),
    )
    with pytest.raises(ClaimsError):
        load_claims(path)


def test_load_claims_rejects_empty_from(tmp_path):
    path = _write(
        tmp_path,
        "claims.json",
        json.dumps([{"id": "auc", "value": 0.9, "from": "  ", "path": "$.a"}]),
    )
    with pytest.raises(ClaimsError):
        load_claims(path)


def test_load_claims_rejects_empty_path(tmp_path):
    path = _write(
        tmp_path,
        "claims.json",
        json.dumps([{"id": "auc", "value": 0.9, "from": "out/x.json", "path": ""}]),
    )
    with pytest.raises(ClaimsError):
        load_claims(path)


# ---------------------------------------------------------------------------
# load_claims() -- table locator ("from" + "column"+"row") [C8 slice 3, Phase 1]
# ---------------------------------------------------------------------------


def _claim(**overrides) -> dict:
    base = {"id": "x", "value": 1.0}
    base.update(overrides)
    return base


def test_load_claims_table_locator_named_tsv_defaults_header_and_delimiter(tmp_path):
    path = _write(
        tmp_path,
        "claims.json",
        json.dumps(
            [
                _claim(
                    **{
                        "from": "results/de.tsv",
                        "column": "log2FoldChange",
                        "row": {"gene_id": "ENSG00000012048"},
                    }
                )
            ]
        ),
    )
    claims = load_claims(path)
    assert claims[0].locator == TableLocator(
        "results/de.tsv", "log2FoldChange", {"gene_id": "ENSG00000012048"}, "\t", True
    )


def test_load_claims_table_locator_named_csv_defaults_header_and_delimiter(tmp_path):
    path = _write(
        tmp_path,
        "claims.json",
        json.dumps(
            [
                _claim(
                    **{
                        "from": "results/de.csv",
                        "column": "log2FoldChange",
                        "row": {"gene_id": "ENSG00000012048"},
                    }
                )
            ]
        ),
    )
    claims = load_claims(path)
    assert claims[0].locator == TableLocator(
        "results/de.csv", "log2FoldChange", {"gene_id": "ENSG00000012048"}, ",", True
    )


def test_load_claims_table_locator_positional_headerless(tmp_path):
    path = _write(
        tmp_path,
        "claims.json",
        json.dumps(
            [_claim(**{"from": "out/counts.csv", "column": 2, "row": 41, "header": False})]
        ),
    )
    claims = load_claims(path)
    assert claims[0].locator == TableLocator("out/counts.csv", 2, 41, ",", False)


def test_load_claims_table_locator_infers_delimiter_from_tsv_gz(tmp_path):
    path = _write(
        tmp_path,
        "claims.json",
        json.dumps([_claim(**{"from": "out/x.tsv.gz", "column": 2, "row": 0, "header": False})]),
    )
    claims = load_claims(path)
    assert claims[0].locator.delimiter == "\t"


def test_load_claims_table_locator_infers_delimiter_from_csv_gz(tmp_path):
    path = _write(
        tmp_path,
        "claims.json",
        json.dumps([_claim(**{"from": "out/x.csv.gz", "column": 2, "row": 0, "header": False})]),
    )
    claims = load_claims(path)
    assert claims[0].locator.delimiter == ","


def test_load_claims_table_locator_explicit_delimiter_overrides_extension(tmp_path):
    path = _write(
        tmp_path,
        "claims.json",
        json.dumps(
            [
                _claim(
                    **{
                        "from": "results/de.tsv",
                        "column": "log2FoldChange",
                        "row": {"gene_id": "X"},
                        "delimiter": ";",
                    }
                )
            ]
        ),
    )
    claims = load_claims(path)
    assert claims[0].locator.delimiter == ";"


def test_load_claims_rejects_path_and_table_fields_together(tmp_path):
    path = _write(
        tmp_path,
        "claims.json",
        json.dumps(
            [
                _claim(
                    **{
                        "from": "out/x.tsv",
                        "path": "$.a",
                        "column": 0,
                        "row": 0,
                        "header": False,
                    }
                )
            ]
        ),
    )
    with pytest.raises(ClaimsError):
        load_claims(path)


def test_load_claims_rejects_column_without_row(tmp_path):
    path = _write(
        tmp_path,
        "claims.json",
        json.dumps([_claim(**{"from": "out/x.tsv", "column": 0})]),
    )
    with pytest.raises(ClaimsError):
        load_claims(path)


def test_load_claims_rejects_row_without_column(tmp_path):
    path = _write(
        tmp_path,
        "claims.json",
        json.dumps([_claim(**{"from": "out/x.tsv", "row": 0})]),
    )
    with pytest.raises(ClaimsError):
        load_claims(path)


def test_load_claims_rejects_column_float(tmp_path):
    path = _write(
        tmp_path,
        "claims.json",
        json.dumps([_claim(**{"from": "out/x.tsv", "column": 1.5, "row": 0})]),
    )
    with pytest.raises(ClaimsError):
        load_claims(path)


def test_load_claims_rejects_column_empty_string(tmp_path):
    path = _write(
        tmp_path,
        "claims.json",
        json.dumps([_claim(**{"from": "out/x.tsv", "column": "", "row": 0})]),
    )
    with pytest.raises(ClaimsError):
        load_claims(path)


def test_load_claims_rejects_column_negative_int(tmp_path):
    path = _write(
        tmp_path,
        "claims.json",
        json.dumps([_claim(**{"from": "out/x.tsv", "column": -1, "row": 0})]),
    )
    with pytest.raises(ClaimsError):
        load_claims(path)


def test_load_claims_rejects_row_negative_int(tmp_path):
    path = _write(
        tmp_path,
        "claims.json",
        json.dumps([_claim(**{"from": "out/x.tsv", "column": "gene_id", "row": -1})]),
    )
    with pytest.raises(ClaimsError):
        load_claims(path)


def test_load_claims_rejects_row_empty_object(tmp_path):
    path = _write(
        tmp_path,
        "claims.json",
        json.dumps([_claim(**{"from": "out/x.tsv", "column": "gene_id", "row": {}})]),
    )
    with pytest.raises(ClaimsError):
        load_claims(path)


def test_load_claims_rejects_row_multi_key_object(tmp_path):
    path = _write(
        tmp_path,
        "claims.json",
        json.dumps(
            [
                _claim(
                    **{
                        "from": "out/x.tsv",
                        "column": "gene_id",
                        "row": {"a": "1", "b": "2"},
                    }
                )
            ]
        ),
    )
    with pytest.raises(ClaimsError):
        load_claims(path)


def test_load_claims_rejects_row_object_empty_key(tmp_path):
    path = _write(
        tmp_path,
        "claims.json",
        json.dumps([_claim(**{"from": "out/x.tsv", "column": "gene_id", "row": {"": "X"}})]),
    )
    with pytest.raises(ClaimsError):
        load_claims(path)


def test_load_claims_rejects_row_object_non_string_value(tmp_path):
    path = _write(
        tmp_path,
        "claims.json",
        json.dumps(
            [_claim(**{"from": "out/x.tsv", "column": "gene_id", "row": {"gene_id": 5}})]
        ),
    )
    with pytest.raises(ClaimsError):
        load_claims(path)


def test_load_claims_rejects_delimiter_not_single_char(tmp_path):
    path = _write(
        tmp_path,
        "claims.json",
        json.dumps(
            [
                _claim(
                    **{
                        "from": "out/x.tsv",
                        "column": "gene_id",
                        "row": 0,
                        "delimiter": ";;",
                    }
                )
            ]
        ),
    )
    with pytest.raises(ClaimsError):
        load_claims(path)


def test_load_claims_rejects_header_not_bool(tmp_path):
    path = _write(
        tmp_path,
        "claims.json",
        json.dumps(
            [_claim(**{"from": "out/x.tsv", "column": "gene_id", "row": 0, "header": "true"})]
        ),
    )
    with pytest.raises(ClaimsError):
        load_claims(path)


def test_load_claims_rejects_table_fields_without_from(tmp_path):
    path = _write(
        tmp_path,
        "claims.json",
        json.dumps([_claim(**{"column": 0, "row": 0})]),
    )
    with pytest.raises(ClaimsError):
        load_claims(path)


def test_load_claims_rejects_row_object_with_header_false(tmp_path):
    path = _write(
        tmp_path,
        "claims.json",
        json.dumps(
            [
                _claim(
                    **{
                        "from": "out/x.tsv",
                        "column": 0,
                        "row": {"gene_id": "X"},
                        "header": False,
                    }
                )
            ]
        ),
    )
    with pytest.raises(ClaimsError):
        load_claims(path)


def test_load_claims_rejects_column_str_with_header_false(tmp_path):
    path = _write(
        tmp_path,
        "claims.json",
        json.dumps(
            [_claim(**{"from": "out/x.tsv", "column": "gene_id", "row": 0, "header": False})]
        ),
    )
    with pytest.raises(ClaimsError):
        load_claims(path)


def test_load_claims_rejects_unknown_extension_without_delimiter(tmp_path):
    path = _write(
        tmp_path,
        "claims.json",
        json.dumps(
            [_claim(**{"from": "results/out.txt", "column": 0, "row": 0, "header": False})]
        ),
    )
    with pytest.raises(ClaimsError):
        load_claims(path)


# ---------------------------------------------------------------------------
# load_claims() -- pattern locator ("pattern", with or without "from") [C8 slice 4, Phase 1]
# ---------------------------------------------------------------------------


def test_load_claims_pattern_without_from_is_stdout_mode(tmp_path):
    path = _write(
        tmp_path,
        "claims.json",
        json.dumps([_claim(**{"pattern": "Final AUC: ([0-9.]+)"})]),
    )
    claims = load_claims(path)
    assert isinstance(claims[0].locator, PatternLocator)
    assert claims[0].locator.source is None
    assert claims[0].locator.pattern == "Final AUC: ([0-9.]+)"


def test_load_claims_pattern_with_from_is_file_mode(tmp_path):
    path = _write(
        tmp_path,
        "claims.json",
        json.dumps(
            [_claim(**{"from": "logs/train.log", "pattern": "Final AUC: ([0-9.]+)"})]
        ),
    )
    claims = load_claims(path)
    assert claims[0].locator == PatternLocator(
        source="logs/train.log", pattern="Final AUC: ([0-9.]+)"
    )


def test_load_claims_pattern_keeps_inline_flags_verbatim(tmp_path):
    path = _write(
        tmp_path,
        "claims.json",
        json.dumps([_claim(**{"pattern": "(?im)^auc = ([0-9.]+)$"})]),
    )
    claims = load_claims(path)
    assert claims[0].locator == PatternLocator(source=None, pattern="(?im)^auc = ([0-9.]+)$")


def test_load_claims_rejects_pattern_with_path(tmp_path):
    path = _write(
        tmp_path,
        "claims.json",
        json.dumps(
            [_claim(**{"from": "out/x.json", "path": "$.auc", "pattern": "auc=([0-9.]+)"})]
        ),
    )
    with pytest.raises(ClaimsError):
        load_claims(path)


def test_load_claims_rejects_pattern_with_column_and_row(tmp_path):
    path = _write(
        tmp_path,
        "claims.json",
        json.dumps(
            [
                _claim(
                    **{
                        "from": "out/x.tsv",
                        "column": 0,
                        "row": 0,
                        "header": False,
                        "pattern": "auc=([0-9.]+)",
                    }
                )
            ]
        ),
    )
    with pytest.raises(ClaimsError):
        load_claims(path)


def test_load_claims_rejects_pattern_with_column_only(tmp_path):
    path = _write(
        tmp_path,
        "claims.json",
        json.dumps([_claim(**{"from": "out/x.tsv", "column": 0, "pattern": "a([0-9])"})]),
    )
    with pytest.raises(ClaimsError):
        load_claims(path)


def test_load_claims_rejects_pattern_with_row_only(tmp_path):
    path = _write(
        tmp_path,
        "claims.json",
        json.dumps([_claim(**{"from": "out/x.tsv", "row": 0, "pattern": "a([0-9])"})]),
    )
    with pytest.raises(ClaimsError):
        load_claims(path)


@pytest.mark.parametrize("field,value", [("header", False), ("delimiter", ";")])
def test_load_claims_rejects_pattern_with_table_only_field_with_from(tmp_path, field, value):
    """`pattern` + `header`/`delimiter` is a contradiction, not a silent ignore.

    The table keys have no meaning for a regex locator; accepting them would be
    a silent misread of the claim's intent.
    """
    path = _write(
        tmp_path,
        "claims.json",
        json.dumps([_claim(**{"from": "logs/train.log", "pattern": "a([0-9])", field: value})]),
    )
    with pytest.raises(ClaimsError):
        load_claims(path)


@pytest.mark.parametrize("field,value", [("header", False), ("delimiter", ";")])
def test_load_claims_rejects_pattern_with_table_only_field_without_from(tmp_path, field, value):
    path = _write(
        tmp_path,
        "claims.json",
        json.dumps([_claim(**{"pattern": "a([0-9])", field: value})]),
    )
    with pytest.raises(ClaimsError):
        load_claims(path)


def test_load_claims_rejects_non_string_pattern(tmp_path):
    path = _write(
        tmp_path,
        "claims.json",
        json.dumps([_claim(**{"pattern": 7})]),
    )
    with pytest.raises(ClaimsError):
        load_claims(path)


def test_load_claims_rejects_empty_pattern(tmp_path):
    path = _write(
        tmp_path,
        "claims.json",
        json.dumps([_claim(**{"pattern": ""})]),
    )
    with pytest.raises(ClaimsError):
        load_claims(path)


def test_load_claims_rejects_blank_pattern(tmp_path):
    path = _write(
        tmp_path,
        "claims.json",
        json.dumps([_claim(**{"pattern": "   "})]),
    )
    with pytest.raises(ClaimsError):
        load_claims(path)


@pytest.mark.parametrize("bad", ["([0-9", "*", "(?P<>x)"])
def test_load_claims_rejects_uncompilable_pattern(tmp_path, bad):
    path = _write(
        tmp_path,
        "claims.json",
        json.dumps([_claim(**{"pattern": bad})]),
    )
    with pytest.raises(ClaimsError):
        load_claims(path)


def test_load_claims_still_rejects_path_without_from(tmp_path):
    path = _write(
        tmp_path,
        "claims.json",
        json.dumps([_claim(**{"path": "$.auc"})]),
    )
    with pytest.raises(ClaimsError):
        load_claims(path)


@pytest.mark.parametrize(
    "field,value",
    [("column", 0), ("row", 0), ("header", False), ("delimiter", ",")],
)
def test_load_claims_still_rejects_table_field_without_from(tmp_path, field, value):
    path = _write(
        tmp_path,
        "claims.json",
        json.dumps([_claim(**{field: value})]),
    )
    with pytest.raises(ClaimsError):
        load_claims(path)


# ---------------------------------------------------------------------------
# load_claims() -- notebook locator (slice 5)
# ---------------------------------------------------------------------------


def test_load_claims_notebook_int_cell_attaches_notebook_locator(tmp_path):
    path = _write(
        tmp_path,
        "claims.json",
        json.dumps(
            [_claim(**{"from": "x.ipynb", "cell": 7, "pattern": "AUC: ([0-9.]+)"})]
        ),
    )
    claims = load_claims(path)
    assert claims[0].locator == NotebookLocator(
        source="x.ipynb", cell=7, pattern="AUC: ([0-9.]+)"
    )


def test_load_claims_notebook_contains_cell_attaches_notebook_locator(tmp_path):
    path = _write(
        tmp_path,
        "claims.json",
        json.dumps(
            [
                _claim(
                    **{
                        "from": "x.ipynb",
                        "cell": {"contains": "print(auc)"},
                        "pattern": "AUC: ([0-9.]+)",
                    }
                )
            ]
        ),
    )
    claims = load_claims(path)
    assert claims[0].locator == NotebookLocator(
        source="x.ipynb", cell={"contains": "print(auc)"}, pattern="AUC: ([0-9.]+)"
    )


def test_load_claims_notebook_rejects_cell_without_from(tmp_path):
    path = _write(
        tmp_path,
        "claims.json",
        json.dumps([_claim(**{"cell": 7, "pattern": "AUC: ([0-9.]+)"})]),
    )
    with pytest.raises(ClaimsError):
        load_claims(path)


def test_load_claims_notebook_rejects_cell_without_pattern(tmp_path):
    path = _write(
        tmp_path,
        "claims.json",
        json.dumps([_claim(**{"from": "x.ipynb", "cell": 7})]),
    )
    with pytest.raises(ClaimsError):
        load_claims(path)


def test_load_claims_notebook_rejects_cell_with_path(tmp_path):
    path = _write(
        tmp_path,
        "claims.json",
        json.dumps(
            [
                _claim(
                    **{
                        "from": "x.ipynb",
                        "cell": 7,
                        "path": "$.auc",
                        "pattern": "AUC: ([0-9.]+)",
                    }
                )
            ]
        ),
    )
    with pytest.raises(ClaimsError):
        load_claims(path)


@pytest.mark.parametrize(
    "field,value",
    [("column", 0), ("row", 0), ("header", False), ("delimiter", ",")],
)
def test_load_claims_notebook_rejects_cell_with_table_field(tmp_path, field, value):
    path = _write(
        tmp_path,
        "claims.json",
        json.dumps(
            [
                _claim(
                    **{
                        "from": "x.ipynb",
                        "cell": 7,
                        "pattern": "AUC: ([0-9.]+)",
                        field: value,
                    }
                )
            ]
        ),
    )
    with pytest.raises(ClaimsError):
        load_claims(path)


def test_load_claims_notebook_rejects_negative_int_cell(tmp_path):
    path = _write(
        tmp_path,
        "claims.json",
        json.dumps(
            [_claim(**{"from": "x.ipynb", "cell": -1, "pattern": "AUC: ([0-9.]+)"})]
        ),
    )
    with pytest.raises(ClaimsError):
        load_claims(path)


def test_load_claims_notebook_rejects_bool_cell(tmp_path):
    path = _write(
        tmp_path,
        "claims.json",
        json.dumps(
            [_claim(**{"from": "x.ipynb", "cell": True, "pattern": "AUC: ([0-9.]+)"})]
        ),
    )
    with pytest.raises(ClaimsError):
        load_claims(path)


def test_load_claims_notebook_rejects_float_cell(tmp_path):
    path = _write(
        tmp_path,
        "claims.json",
        json.dumps(
            [_claim(**{"from": "x.ipynb", "cell": 1.5, "pattern": "AUC: ([0-9.]+)"})]
        ),
    )
    with pytest.raises(ClaimsError):
        load_claims(path)


def test_load_claims_notebook_rejects_cell_dict_without_contains(tmp_path):
    path = _write(
        tmp_path,
        "claims.json",
        json.dumps(
            [
                _claim(
                    **{
                        "from": "x.ipynb",
                        "cell": {"startswith": "print"},
                        "pattern": "AUC: ([0-9.]+)",
                    }
                )
            ]
        ),
    )
    with pytest.raises(ClaimsError):
        load_claims(path)


def test_load_claims_notebook_rejects_cell_contains_empty(tmp_path):
    path = _write(
        tmp_path,
        "claims.json",
        json.dumps(
            [
                _claim(
                    **{
                        "from": "x.ipynb",
                        "cell": {"contains": ""},
                        "pattern": "AUC: ([0-9.]+)",
                    }
                )
            ]
        ),
    )
    with pytest.raises(ClaimsError):
        load_claims(path)


def test_load_claims_notebook_rejects_cell_contains_non_string(tmp_path):
    path = _write(
        tmp_path,
        "claims.json",
        json.dumps(
            [
                _claim(
                    **{
                        "from": "x.ipynb",
                        "cell": {"contains": 5},
                        "pattern": "AUC: ([0-9.]+)",
                    }
                )
            ]
        ),
    )
    with pytest.raises(ClaimsError):
        load_claims(path)


def test_load_claims_notebook_rejects_cell_dict_with_extra_key(tmp_path):
    path = _write(
        tmp_path,
        "claims.json",
        json.dumps(
            [
                _claim(
                    **{
                        "from": "x.ipynb",
                        "cell": {"contains": "print(auc)", "nth": 2},
                        "pattern": "AUC: ([0-9.]+)",
                    }
                )
            ]
        ),
    )
    with pytest.raises(ClaimsError):
        load_claims(path)


@pytest.mark.parametrize("bad", ["([0-9", "*", "(?P<>x)"])
def test_load_claims_notebook_rejects_uncompilable_pattern_with_cell(tmp_path, bad):
    path = _write(
        tmp_path,
        "claims.json",
        json.dumps([_claim(**{"from": "x.ipynb", "cell": 7, "pattern": bad})]),
    )
    with pytest.raises(ClaimsError):
        load_claims(path)


def test_load_claims_notebook_rejects_empty_pattern_with_cell(tmp_path):
    path = _write(
        tmp_path,
        "claims.json",
        json.dumps([_claim(**{"from": "x.ipynb", "cell": 7, "pattern": ""})]),
    )
    with pytest.raises(ClaimsError):
        load_claims(path)


# --- back-compat: a claim with no `cell` is byte-identical to slices 1.5/3/4 ---


def test_load_claims_pattern_no_cell_still_pattern_locator(tmp_path):
    path = _write(
        tmp_path,
        "claims.json",
        json.dumps([_claim(**{"from": "log.txt", "pattern": "AUC: ([0-9.]+)"})]),
    )
    claims = load_claims(path)
    assert claims[0].locator == PatternLocator(
        source="log.txt", pattern="AUC: ([0-9.]+)"
    )


def test_load_claims_path_no_cell_still_json_locator(tmp_path):
    path = _write(
        tmp_path,
        "claims.json",
        json.dumps([_claim(**{"from": "x.json", "path": "$.a"})]),
    )
    claims = load_claims(path)
    assert claims[0].locator == Locator(source="x.json", path="$.a")


def test_load_claims_table_no_cell_still_table_locator(tmp_path):
    path = _write(
        tmp_path,
        "claims.json",
        json.dumps(
            [_claim(**{"from": "t.tsv", "column": 0, "row": 0, "header": False})]
        ),
    )
    claims = load_claims(path)
    assert claims[0].locator == TableLocator(
        source="t.tsv", column=0, row=0, delimiter="\t", header=False
    )


# ---------------------------------------------------------------------------
# run_reproduction()
# ---------------------------------------------------------------------------


def _fake_executor(
    exit_code: int, results: dict | None, results_path: str = "results.json", output: str = ""
):
    """Build a fake executor that writes `results` into `repo/results_path`
    (unless `results` is None, in which case no file is written) and returns
    `(exit_code, output)`. Mirrors the injected
    `Callable[[list[str], Path], tuple[int, str]]` seam.
    """

    def executor(argv: list[str], repo: Path) -> tuple[int, str]:
        if results is not None:
            (repo / results_path).write_text(json.dumps(results))
        return exit_code, output

    return executor


def _claims(*specs: tuple[str, float, float]) -> list[Claim]:
    return [Claim(id=cid, value=value, tolerance=tol) for cid, value, tol in specs]


def test_run_reproduction_missing_claim_key_is_unverified(tmp_path):
    claims = _claims(("auc", 0.9, 0.05), ("accuracy", 0.8, 0.05))
    executor = _fake_executor(0, {"auc": 0.9})
    record = run_reproduction(
        repo=str(tmp_path),
        run_command="echo run",
        claims=claims,
        executor=executor,
        claims_sha256="a" * 64,
        created_at="2026-07-18T00:00:00Z",
        reproduce_id="rp_1",
        run_started_at=_RUN_START,
    )
    by_id = {r.id: r for r in record.claim_results}
    assert by_id["auc"].status == "reproduced"
    assert by_id["accuracy"].status == "unverified"
    assert by_id["accuracy"].observed is None


def test_run_reproduction_non_numeric_string_observed_is_unverified(tmp_path):
    claims = _claims(("auc", 0.9, 0.05))
    executor = _fake_executor(0, {"auc": "high"})
    record = run_reproduction(
        repo=str(tmp_path),
        run_command="echo run",
        claims=claims,
        executor=executor,
        claims_sha256="a" * 64,
        created_at="2026-07-18T00:00:00Z",
        reproduce_id="rp_1",
        run_started_at=_RUN_START,
    )
    assert record.claim_results[0].status == "unverified"
    assert record.claim_results[0].observed is None


def test_run_reproduction_boolean_observed_is_unverified(tmp_path):
    claims = _claims(("auc", 0.9, 0.05))
    executor = _fake_executor(0, {"auc": True})
    record = run_reproduction(
        repo=str(tmp_path),
        run_command="echo run",
        claims=claims,
        executor=executor,
        claims_sha256="a" * 64,
        created_at="2026-07-18T00:00:00Z",
        reproduce_id="rp_1",
        run_started_at=_RUN_START,
    )
    assert record.claim_results[0].status == "unverified"
    assert record.claim_results[0].observed is None


def test_run_reproduction_nonzero_exit_marks_all_unverified_and_skips_results(tmp_path):
    claims = _claims(("auc", 0.9, 0.05), ("accuracy", 0.8, 0.05))
    # Even if a results file exists, a nonzero exit must short-circuit before reading it.
    executor = _fake_executor(1, {"auc": 0.9, "accuracy": 0.8})
    record = run_reproduction(
        repo=str(tmp_path),
        run_command="false",
        claims=claims,
        executor=executor,
        claims_sha256="a" * 64,
        created_at="2026-07-18T00:00:00Z",
        reproduce_id="rp_1",
        run_started_at=_RUN_START,
    )
    assert record.exit_code == 1
    assert all(r.status == "unverified" for r in record.claim_results)
    assert all(r.observed is None for r in record.claim_results)
    assert "exit 1" in record.claim_results[0].message


def test_run_reproduction_missing_results_file_marks_all_unverified(tmp_path):
    claims = _claims(("auc", 0.9, 0.05))
    executor = _fake_executor(0, results=None)  # exit 0, but never writes results.json
    record = run_reproduction(
        repo=str(tmp_path),
        run_command="echo run",
        claims=claims,
        executor=executor,
        claims_sha256="a" * 64,
        created_at="2026-07-18T00:00:00Z",
        reproduce_id="rp_1",
        run_started_at=_RUN_START,
    )
    assert record.claim_results[0].status == "unverified"
    assert record.claim_results[0].observed is None


def test_run_reproduction_unparseable_results_file_marks_all_unverified(tmp_path):
    claims = _claims(("auc", 0.9, 0.05))

    def executor(argv, repo):
        (repo / "results.json").write_text("{not json")
        return 0, ""

    record = run_reproduction(
        repo=str(tmp_path),
        run_command="echo run",
        claims=claims,
        executor=executor,
        claims_sha256="a" * 64,
        created_at="2026-07-18T00:00:00Z",
        reproduce_id="rp_1",
        run_started_at=_RUN_START,
    )
    assert record.claim_results[0].status == "unverified"
    assert record.claim_results[0].observed is None


def test_run_reproduction_extra_results_keys_are_ignored(tmp_path):
    claims = _claims(("auc", 0.9, 0.05))
    executor = _fake_executor(0, {"auc": 0.9, "unrelated_metric": 42})
    record = run_reproduction(
        repo=str(tmp_path),
        run_command="echo run",
        claims=claims,
        executor=executor,
        claims_sha256="a" * 64,
        created_at="2026-07-18T00:00:00Z",
        reproduce_id="rp_1",
        run_started_at=_RUN_START,
    )
    assert len(record.claim_results) == 1
    assert record.claim_results[0].status == "reproduced"


def test_run_reproduction_returns_full_record_metadata(tmp_path):
    claims = _claims(("auc", 0.9, 0.05))
    executor = _fake_executor(0, {"auc": 0.9})
    record = run_reproduction(
        repo=str(tmp_path),
        run_command="echo run",
        claims=claims,
        executor=executor,
        claims_sha256="a" * 64,
        created_at="2026-07-18T00:00:00Z",
        reproduce_id="rp_1",
        run_started_at=_RUN_START,
    )
    assert record.reproduce_id == "rp_1"
    assert record.repo == str(tmp_path)
    assert record.run_command == "echo run"
    assert record.claims_sha256 == "a" * 64
    assert record.created_at == "2026-07-18T00:00:00Z"
    assert record.exit_code == 0


# ---------------------------------------------------------------------------
# run_reproduction() -- located claims via the output locator [C8 slice 1.5,
# Phase 3]
# ---------------------------------------------------------------------------


def _run(tmp_path: Path, claims: list[Claim], executor, **overrides) -> "object":
    kwargs = dict(
        repo=str(tmp_path),
        run_command="echo run",
        claims=claims,
        executor=executor,
        claims_sha256="a" * 64,
        created_at="2026-07-18T00:00:00Z",
        reproduce_id="rp_1",
        run_started_at=_RUN_START,
    )
    kwargs.update(overrides)
    return run_reproduction(**kwargs)


def _write_located(tmp_path: Path, rel: str, payload: object) -> None:
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload))


def _noop_executor(exit_code: int = 0):
    def executor(argv: list[str], repo: Path) -> tuple[int, str]:
        return exit_code, ""

    return executor


def test_run_reproduction_located_claim_matching_is_reproduced(tmp_path):
    _write_located(tmp_path, "out/summary.json", {"model": {"auc": 0.9}})
    claims = [Claim(id="auc", value=0.9, tolerance=0.05, locator=Locator("out/summary.json", "$.model.auc"))]
    record = _run(tmp_path, claims, _noop_executor())
    result = record.claim_results[0]
    assert result.status == "reproduced"
    assert result.observed == 0.9


def test_run_reproduction_located_claim_stale_exact_match_is_unverified(tmp_path):
    # THE headline test: a JSON output file the run did NOT rewrite (mtime
    # predates run start) is UNVERIFIED even when its stored value matches
    # the claim exactly -- an author's committed artifact must never
    # produce a false REPRODUCED. Mirrors
    # test_run_reproduction_notebook_stale_exact_match_is_unverified.
    p = tmp_path / "out/summary.json"
    _write_located(tmp_path, "out/summary.json", {"model": {"auc": 0.9}})
    os.utime(p, (_RUN_START - 10, _RUN_START - 10))
    claims = [Claim(id="auc", value=0.9, tolerance=0.05, locator=Locator("out/summary.json", "$.model.auc"))]
    record = _run(tmp_path, claims, _noop_executor(), run_started_at=_RUN_START)
    result = record.claim_results[0]
    assert result.status == "unverified"
    assert result.observed is None
    assert "rewritten" in result.message
    assert "run start" in result.message


def test_run_reproduction_located_claim_fresh_still_reproduces(tmp_path):
    p = tmp_path / "out/summary.json"
    _write_located(tmp_path, "out/summary.json", {"model": {"auc": 0.9}})
    os.utime(p, (_RUN_START + 5, _RUN_START + 5))
    claims = [Claim(id="auc", value=0.9, tolerance=0.05, locator=Locator("out/summary.json", "$.model.auc"))]
    record = _run(tmp_path, claims, _noop_executor(), run_started_at=_RUN_START)
    result = record.claim_results[0]
    assert result.status == "reproduced"
    assert result.observed == 0.9


def test_run_reproduction_located_claim_missing_run_started_at_raises(tmp_path):
    # An unstamped run start is a programming error, not a silent
    # UNVERIFIED -- a None meaning "guard off" would silently disable a
    # false-pass guard.
    p = tmp_path / "out/summary.json"
    _write_located(tmp_path, "out/summary.json", {"model": {"auc": 0.9}})
    os.utime(p, (_RUN_START + 5, _RUN_START + 5))
    claims = [Claim(id="auc", value=0.9, tolerance=0.05, locator=Locator("out/summary.json", "$.model.auc"))]
    with pytest.raises(ValueError):
        _run(tmp_path, claims, _noop_executor(), run_started_at=None)


def test_run_reproduction_located_claim_drifted_is_diverged_with_message(tmp_path):
    _write_located(tmp_path, "out/summary.json", {"model": {"auc": 0.5}})
    claims = [Claim(id="auc", value=0.9, tolerance=0.05, locator=Locator("out/summary.json", "$.model.auc"))]
    record = _run(tmp_path, claims, _noop_executor())
    result = record.claim_results[0]
    assert result.status == "diverged"
    assert result.observed == 0.5
    assert "0.5" in result.message
    assert "0.9" in result.message
    assert result.delta is not None


def test_run_reproduction_located_claim_near_value_is_within_tolerance(tmp_path):
    _write_located(tmp_path, "out/summary.json", {"model": {"auc": 0.92}})
    claims = [Claim(id="auc", value=0.9, tolerance=0.05, locator=Locator("out/summary.json", "$.model.auc"))]
    record = _run(tmp_path, claims, _noop_executor())
    result = record.claim_results[0]
    assert result.status == "within_tolerance"
    assert result.observed == 0.92


def test_run_reproduction_located_claim_missing_file_is_unverified(tmp_path):
    claims = [Claim(id="auc", value=0.9, tolerance=0.05, locator=Locator("out/summary.json", "$.model.auc"))]
    record = _run(tmp_path, claims, _noop_executor())
    result = record.claim_results[0]
    assert result.status == "unverified"
    assert result.observed is None


def test_run_reproduction_located_claim_unparseable_json_is_unverified(tmp_path):
    p = tmp_path / "out" / "summary.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("{not json")
    claims = [Claim(id="auc", value=0.9, tolerance=0.05, locator=Locator("out/summary.json", "$.model.auc"))]
    record = _run(tmp_path, claims, _noop_executor())
    result = record.claim_results[0]
    assert result.status == "unverified"
    assert result.observed is None


def test_run_reproduction_located_claim_non_utf8_file_is_unverified_not_raise(tmp_path):
    # A non-UTF-8 'from' file makes Path.read_text() raise UnicodeDecodeError,
    # a ValueError subclass -- must be caught alongside JSONDecodeError/OSError
    # and mapped to unverified, never propagate and crash the run.
    (tmp_path / "out").mkdir()
    (tmp_path / "out" / "summary.json").write_bytes(b"\xff\xfe\x00bad")
    claims = [Claim(id="auc", value=0.9, tolerance=0.05, locator=Locator("out/summary.json", "$.model.auc"))]
    record = _run(tmp_path, claims, _noop_executor())
    result = record.claim_results[0]
    assert result.status == "unverified"
    assert result.observed is None
    assert "not valid JSON" in result.message


def test_run_reproduction_located_claim_unresolved_path_is_unverified(tmp_path):
    _write_located(tmp_path, "out/summary.json", {"model": {"acc": 0.9}})
    claims = [Claim(id="auc", value=0.9, tolerance=0.05, locator=Locator("out/summary.json", "$.model.auc"))]
    record = _run(tmp_path, claims, _noop_executor())
    result = record.claim_results[0]
    assert result.status == "unverified"
    assert result.observed is None


def test_run_reproduction_located_claim_string_target_is_unverified_strict(tmp_path):
    _write_located(tmp_path, "out/summary.json", {"model": {"auc": "0.9"}})
    claims = [Claim(id="auc", value=0.9, tolerance=0.05, locator=Locator("out/summary.json", "$.model.auc"))]
    record = _run(tmp_path, claims, _noop_executor())
    result = record.claim_results[0]
    assert result.status == "unverified"
    assert result.observed is None


def test_run_reproduction_located_claim_numeric_string_target_is_unverified_strict(tmp_path):
    _write_located(tmp_path, "out/summary.json", {"model": {"auc": "0.91"}})
    claims = [Claim(id="auc", value=0.9, tolerance=0.05, locator=Locator("out/summary.json", "$.model.auc"))]
    record = _run(tmp_path, claims, _noop_executor())
    result = record.claim_results[0]
    assert result.status == "unverified"
    assert result.observed is None


def test_run_reproduction_located_claim_boolean_target_is_unverified(tmp_path):
    _write_located(tmp_path, "out/summary.json", {"model": {"auc": True}})
    claims = [Claim(id="auc", value=0.9, tolerance=0.05, locator=Locator("out/summary.json", "$.model.auc"))]
    record = _run(tmp_path, claims, _noop_executor())
    result = record.claim_results[0]
    assert result.status == "unverified"
    assert result.observed is None


def test_run_reproduction_located_claim_nan_target_is_unverified(tmp_path):
    # JSON has no literal NaN/Infinity by spec, but Python's json module accepts
    # them by default (json.dumps(float("nan")) -> "NaN"); write raw text.
    p = tmp_path / "out" / "summary.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text('{"model": {"auc": NaN}}')
    claims = [Claim(id="auc", value=0.9, tolerance=0.05, locator=Locator("out/summary.json", "$.model.auc"))]
    record = _run(tmp_path, claims, _noop_executor())
    result = record.claim_results[0]
    assert result.status == "unverified"
    assert result.observed is None


def test_run_reproduction_located_claim_inf_target_is_unverified(tmp_path):
    p = tmp_path / "out" / "summary.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text('{"model": {"auc": Infinity}}')
    claims = [Claim(id="auc", value=0.9, tolerance=0.05, locator=Locator("out/summary.json", "$.model.auc"))]
    record = _run(tmp_path, claims, _noop_executor())
    result = record.claim_results[0]
    assert result.status == "unverified"
    assert result.observed is None


def test_run_reproduction_mixed_located_and_flat_claims_resolve_independently(tmp_path):
    _write_located(tmp_path, "out/summary.json", {"model": {"auc": 0.9}})
    located = Claim(id="auc", value=0.9, tolerance=0.05, locator=Locator("out/summary.json", "$.model.auc"))
    flat = Claim(id="accuracy", value=0.8, tolerance=0.05)
    executor = _fake_executor(0, {"accuracy": 0.8})
    record = _run(tmp_path, [located, flat], executor)
    by_id = {r.id: r for r in record.claim_results}
    assert by_id["auc"].status == "reproduced"
    assert by_id["auc"].observed == 0.9
    assert by_id["accuracy"].status == "reproduced"
    assert by_id["accuracy"].observed == 0.8


def test_run_reproduction_located_claim_escaping_repo_is_unverified_and_not_read(tmp_path):
    # A real file outside the repo dir, with a value that WOULD reproduce if read.
    outside_dir = tmp_path.parent / "outside_secret"
    outside_dir.mkdir(exist_ok=True)
    secret_file = outside_dir / "secret.json"
    secret_file.write_text(json.dumps({"model": {"auc": 0.9}}))

    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    claims = [
        Claim(
            id="auc",
            value=0.9,
            tolerance=0.05,
            locator=Locator("../outside_secret/secret.json", "$.model.auc"),
        )
    ]
    record = run_reproduction(
        repo=str(repo_dir),
        run_command="echo run",
        claims=claims,
        executor=_noop_executor(),
        claims_sha256="a" * 64,
        created_at="2026-07-18T00:00:00Z",
        reproduce_id="rp_1",
        run_started_at=_RUN_START,
    )
    result = record.claim_results[0]
    assert result.status == "unverified"
    assert result.observed is None
    assert "escapes the repo" in result.message


def test_run_reproduction_located_claim_nonzero_exit_is_unverified(tmp_path):
    _write_located(tmp_path, "out/summary.json", {"model": {"auc": 0.9}})
    claims = [Claim(id="auc", value=0.9, tolerance=0.05, locator=Locator("out/summary.json", "$.model.auc"))]
    record = _run(tmp_path, claims, _noop_executor(exit_code=1))
    result = record.claim_results[0]
    assert result.status == "unverified"
    assert result.observed is None
    assert "exit 1" in result.message


# ---------------------------------------------------------------------------
# run_reproduction() -- located claims via the TSV/CSV table locator
# [C8 slice 3, Phase 3]
# ---------------------------------------------------------------------------

_DE_HEADER = ["gene_id", "log2FoldChange", "padj"]


def _write_tsv(tmp_path: Path, rel: str, rows: list[list[str]]) -> None:
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join("\t".join(row) for row in rows) + "\n")


def _write_csv(tmp_path: Path, rel: str, rows: list[list[str]]) -> None:
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(",".join(row) for row in rows) + "\n")


def test_run_reproduction_table_claim_named_matching_is_reproduced(tmp_path):
    _write_tsv(
        tmp_path,
        "out/de.tsv",
        [_DE_HEADER, ["ENSG1", "-2.31", "0.001"], ["ENSG2", "0.5", "0.2"]],
    )
    claims = [
        Claim(
            id="log2fc",
            value=-2.31,
            tolerance=0.05,
            locator=TableLocator(
                "out/de.tsv", "log2FoldChange", {"gene_id": "ENSG1"}, "\t", True
            ),
        )
    ]
    record = _run(tmp_path, claims, _noop_executor())
    result = record.claim_results[0]
    assert result.status == "reproduced"
    assert result.observed == -2.31


def test_run_reproduction_table_claim_drifted_is_diverged_with_message(tmp_path):
    _write_tsv(tmp_path, "out/de.tsv", [_DE_HEADER, ["ENSG1", "-1.0", "0.001"]])
    claims = [
        Claim(
            id="log2fc",
            value=-2.31,
            tolerance=0.05,
            locator=TableLocator(
                "out/de.tsv", "log2FoldChange", {"gene_id": "ENSG1"}, "\t", True
            ),
        )
    ]
    record = _run(tmp_path, claims, _noop_executor())
    result = record.claim_results[0]
    assert result.status == "diverged"
    assert result.observed == -1.0
    assert "-1.0" in result.message
    assert "-2.31" in result.message
    assert result.delta is not None


def test_run_reproduction_table_claim_near_value_is_within_tolerance(tmp_path):
    _write_tsv(tmp_path, "out/de.tsv", [_DE_HEADER, ["ENSG1", "-2.3", "0.001"]])
    claims = [
        Claim(
            id="log2fc",
            value=-2.31,
            tolerance=0.05,
            locator=TableLocator(
                "out/de.tsv", "log2FoldChange", {"gene_id": "ENSG1"}, "\t", True
            ),
        )
    ]
    record = _run(tmp_path, claims, _noop_executor())
    result = record.claim_results[0]
    assert result.status == "within_tolerance"
    assert result.observed == -2.3


def test_run_reproduction_table_claim_positional_headerless_resolves(tmp_path):
    _write_csv(tmp_path, "out/counts.csv", [["ENSG1", "10", "20"], ["ENSG2", "30.4", "40"]])
    claims = [
        Claim(
            id="count",
            value=30.4,
            tolerance=0.05,
            locator=TableLocator("out/counts.csv", 1, 1, ",", False),
        )
    ]
    record = _run(tmp_path, claims, _noop_executor())
    result = record.claim_results[0]
    assert result.status == "reproduced"
    assert result.observed == 30.4


def test_run_reproduction_table_claim_missing_file_is_unverified(tmp_path):
    claims = [
        Claim(
            id="log2fc",
            value=-2.31,
            tolerance=0.05,
            locator=TableLocator(
                "out/de.tsv", "log2FoldChange", {"gene_id": "ENSG1"}, "\t", True
            ),
        )
    ]
    record = _run(tmp_path, claims, _noop_executor())
    result = record.claim_results[0]
    assert result.status == "unverified"
    assert result.observed is None


def test_run_reproduction_table_claim_truncated_gzip_is_unverified(tmp_path):
    # A truncated .tsv.gz raises EOFError from stdlib gzip (not OSError) --
    # the engine must degrade the claim to unverified, never raise or
    # diverge. Regression for the C8 slice 3 review finding.
    p = tmp_path / "out" / "de.tsv.gz"
    p.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(p, "wt", encoding="utf-8", newline="") as f:
        f.write("gene_id\tlog2FoldChange\tpadj\nENSG1\t-2.31\t0.001\n")
    full_bytes = p.read_bytes()
    p.write_bytes(full_bytes[: len(full_bytes) // 2])
    claims = [
        Claim(
            id="log2fc",
            value=-2.31,
            tolerance=0.05,
            locator=TableLocator(
                "out/de.tsv.gz", "log2FoldChange", {"gene_id": "ENSG1"}, "\t", True
            ),
        )
    ]
    record = _run(tmp_path, claims, _noop_executor())
    result = record.claim_results[0]
    assert result.status == "unverified"
    assert result.observed is None


def test_run_reproduction_table_claim_unresolved_column_is_unverified(tmp_path):
    _write_tsv(tmp_path, "out/de.tsv", [_DE_HEADER, ["ENSG1", "-2.31", "0.001"]])
    claims = [
        Claim(
            id="log2fc",
            value=-2.31,
            tolerance=0.05,
            locator=TableLocator("out/de.tsv", "nonexistent_col", 0, "\t", True),
        )
    ]
    record = _run(tmp_path, claims, _noop_executor())
    result = record.claim_results[0]
    assert result.status == "unverified"
    assert result.observed is None
    assert "nonexistent_col" in result.message


def test_run_reproduction_table_claim_row_key_zero_matches_is_unverified(tmp_path):
    _write_tsv(tmp_path, "out/de.tsv", [_DE_HEADER, ["ENSG1", "-2.31", "0.001"]])
    claims = [
        Claim(
            id="log2fc",
            value=-2.31,
            tolerance=0.05,
            locator=TableLocator("out/de.tsv", "log2FoldChange", {"gene_id": "NOPE"}, "\t", True),
        )
    ]
    record = _run(tmp_path, claims, _noop_executor())
    result = record.claim_results[0]
    assert result.status == "unverified"
    assert result.observed is None
    assert "0 rows" in result.message


def test_run_reproduction_table_claim_row_key_many_matches_is_unverified(tmp_path):
    _write_tsv(
        tmp_path,
        "out/de.tsv",
        [_DE_HEADER, ["ENSG1", "-2.31", "0.001"], ["ENSG1", "-5.0", "0.02"]],
    )
    claims = [
        Claim(
            id="log2fc",
            value=-2.31,
            tolerance=0.05,
            locator=TableLocator(
                "out/de.tsv", "log2FoldChange", {"gene_id": "ENSG1"}, "\t", True
            ),
        )
    ]
    record = _run(tmp_path, claims, _noop_executor())
    result = record.claim_results[0]
    assert result.status == "unverified"
    assert result.observed is None
    assert "2 rows" in result.message


def test_run_reproduction_table_claim_ragged_row_is_unverified(tmp_path):
    p = tmp_path / "out" / "de.tsv"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("gene_id\tlog2FoldChange\tpadj\nENSG1\n")
    claims = [
        Claim(
            id="log2fc",
            value=-2.31,
            tolerance=0.05,
            locator=TableLocator("out/de.tsv", "log2FoldChange", 0, "\t", True),
        )
    ]
    record = _run(tmp_path, claims, _noop_executor())
    result = record.claim_results[0]
    assert result.status == "unverified"
    assert result.observed is None


def test_run_reproduction_table_claim_unparseable_cell_is_unverified(tmp_path):
    _write_tsv(tmp_path, "out/de.tsv", [_DE_HEADER, ["ENSG1", "NA", "0.001"]])
    claims = [
        Claim(
            id="log2fc",
            value=-2.31,
            tolerance=0.05,
            locator=TableLocator("out/de.tsv", "log2FoldChange", 0, "\t", True),
        )
    ]
    record = _run(tmp_path, claims, _noop_executor())
    result = record.claim_results[0]
    assert result.status == "unverified"
    assert result.observed is None


def test_run_reproduction_table_claim_non_finite_cell_is_unverified(tmp_path):
    _write_tsv(tmp_path, "out/de.tsv", [_DE_HEADER, ["ENSG1", "inf", "0.001"]])
    claims = [
        Claim(
            id="log2fc",
            value=-2.31,
            tolerance=0.05,
            locator=TableLocator("out/de.tsv", "log2FoldChange", 0, "\t", True),
        )
    ]
    record = _run(tmp_path, claims, _noop_executor())
    result = record.claim_results[0]
    assert result.status == "unverified"
    assert result.observed is None


def test_run_reproduction_table_claim_numeric_string_cell_is_the_observed_value(tmp_path):
    # Deliberate divergence from the JSON locator rule: every table cell is a
    # string, so a numeric-looking string like "30.4" is the NORMAL valid
    # case and must classify -- not go unverified.
    _write_tsv(tmp_path, "out/counts.tsv", [["gene_id", "count"], ["ENSG1", "30.4"]])
    claims = [
        Claim(
            id="count",
            value=30.4,
            tolerance=0.05,
            locator=TableLocator("out/counts.tsv", "count", 0, "\t", True),
        )
    ]
    record = _run(tmp_path, claims, _noop_executor())
    result = record.claim_results[0]
    assert result.status == "reproduced"
    assert result.observed == 30.4


def test_run_reproduction_table_claim_same_file_parsed_once(tmp_path, monkeypatch):
    _write_tsv(
        tmp_path,
        "out/de.tsv",
        [_DE_HEADER, ["ENSG1", "-2.31", "0.001"], ["ENSG2", "0.5", "0.2"]],
    )
    calls: list[Path] = []
    original_read_table = reproduce_module._read_table

    def counting_read_table(path, delimiter):
        calls.append(path)
        return original_read_table(path, delimiter)

    monkeypatch.setattr(reproduce_module, "_read_table", counting_read_table)

    claims = [
        Claim(
            id="log2fc_1",
            value=-2.31,
            tolerance=0.05,
            locator=TableLocator(
                "out/de.tsv", "log2FoldChange", {"gene_id": "ENSG1"}, "\t", True
            ),
        ),
        Claim(
            id="log2fc_2",
            value=0.5,
            tolerance=0.05,
            locator=TableLocator(
                "out/de.tsv", "log2FoldChange", {"gene_id": "ENSG2"}, "\t", True
            ),
        ),
    ]
    record = _run(tmp_path, claims, _noop_executor())
    by_id = {r.id: r for r in record.claim_results}
    assert by_id["log2fc_1"].status == "reproduced"
    assert by_id["log2fc_2"].status == "reproduced"
    assert len(calls) == 1


def test_run_reproduction_mixed_table_and_json_and_flat_claims_resolve_independently(tmp_path):
    _write_located(tmp_path, "out/summary.json", {"model": {"auc": 0.9}})
    _write_tsv(tmp_path, "out/de.tsv", [_DE_HEADER, ["ENSG1", "-2.31", "0.001"]])
    table_claim = Claim(
        id="log2fc",
        value=-2.31,
        tolerance=0.05,
        locator=TableLocator("out/de.tsv", "log2FoldChange", 0, "\t", True),
    )
    json_claim = Claim(
        id="auc", value=0.9, tolerance=0.05, locator=Locator("out/summary.json", "$.model.auc")
    )
    flat_claim = Claim(id="accuracy", value=0.8, tolerance=0.05)
    executor = _fake_executor(0, {"accuracy": 0.8})
    record = _run(tmp_path, [table_claim, json_claim, flat_claim], executor)
    by_id = {r.id: r for r in record.claim_results}
    assert by_id["log2fc"].status == "reproduced"
    assert by_id["auc"].status == "reproduced"
    assert by_id["accuracy"].status == "reproduced"


def test_run_reproduction_table_claim_escaping_repo_is_unverified_and_not_read(
    tmp_path, monkeypatch
):
    outside_dir = tmp_path.parent / "outside_table_secret"
    outside_dir.mkdir(exist_ok=True)
    secret_file = outside_dir / "secret.tsv"
    secret_file.write_text("gene_id\tlog2FoldChange\nENSG1\t-2.31\n")

    calls: list[Path] = []
    original_read_table = reproduce_module._read_table

    def counting_read_table(path, delimiter):
        calls.append(path)
        return original_read_table(path, delimiter)

    monkeypatch.setattr(reproduce_module, "_read_table", counting_read_table)

    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    claims = [
        Claim(
            id="log2fc",
            value=-2.31,
            tolerance=0.05,
            locator=TableLocator(
                "../outside_table_secret/secret.tsv",
                "log2FoldChange",
                {"gene_id": "ENSG1"},
                "\t",
                True,
            ),
        )
    ]
    record = run_reproduction(
        repo=str(repo_dir),
        run_command="echo run",
        claims=claims,
        executor=_noop_executor(),
        claims_sha256="a" * 64,
        created_at="2026-07-18T00:00:00Z",
        reproduce_id="rp_1",
        run_started_at=_RUN_START,
    )
    result = record.claim_results[0]
    assert result.status == "unverified"
    assert result.observed is None
    assert "escapes the repo" in result.message
    assert calls == []


def test_run_reproduction_table_claim_nonzero_exit_is_unverified(tmp_path):
    _write_tsv(tmp_path, "out/de.tsv", [_DE_HEADER, ["ENSG1", "-2.31", "0.001"]])
    claims = [
        Claim(
            id="log2fc",
            value=-2.31,
            tolerance=0.05,
            locator=TableLocator("out/de.tsv", "log2FoldChange", 0, "\t", True),
        )
    ]
    record = _run(tmp_path, claims, _noop_executor(exit_code=1))
    result = record.claim_results[0]
    assert result.status == "unverified"
    assert result.observed is None
    assert "exit 1" in result.message


# ---------------------------------------------------------------------------
# run_reproduction() -- located claims via the stdout/log pattern locator
# [C8 slice 4, Phase 3]
# ---------------------------------------------------------------------------


def _write_log(tmp_path: Path, rel: str, text: str) -> None:
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)


def _spy_read_text(monkeypatch) -> list[Path]:
    """Record every `Path.read_text()` call. Used to prove the engine never
    touches the filesystem for a stdout-mode pattern claim, never reads a
    file that escapes the repo or is oversized, and reads a shared log once.
    """
    calls: list[Path] = []
    original = Path.read_text

    def spy(self, *args, **kwargs):
        calls.append(Path(self))
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", spy)
    return calls


class _ScriptedExecutor:
    """Returns scripted `(exit_code, output)` tuples in call order (copied
    from tests/test_reproduce_env_resurrection.py -- the local `_fake_executor`
    only ever scripts a single call, and the retried-output binding needs two).
    """

    def __init__(self, script, results_by_call=None, results_path="results.json"):
        self.script = list(script)
        self.results_by_call = results_by_call or {}
        self.results_path = results_path
        self.calls = 0

    def __call__(self, argv: list[str], repo: Path) -> tuple[int, str]:
        self.calls += 1
        if self.calls in self.results_by_call:
            (Path(repo) / self.results_path).write_text(
                json.dumps(self.results_by_call[self.calls])
            )
        return self.script[self.calls - 1]


class _ScriptedInstaller:
    """Records every `(argv, cwd)` it was called with and always returns the
    same scripted exit code."""

    def __init__(self, return_code: int):
        self.return_code = return_code
        self.calls: list[tuple[list[str], Path]] = []

    def __call__(self, cmd: list[str], cwd: Path) -> int:
        self.calls.append((list(cmd), cwd))
        return self.return_code


def test_run_reproduction_pattern_claim_stdout_matching_is_reproduced(tmp_path):
    # No results file is ever written: the observed value comes purely from
    # the run's captured output.
    executor = _fake_executor(0, results=None, output="Final AUC: 0.91\n")
    claims = [
        Claim(
            id="auc",
            value=0.91,
            tolerance=0.05,
            locator=PatternLocator(None, r"Final AUC: ([0-9.]+)"),
        )
    ]
    record = _run(tmp_path, claims, executor)
    result = record.claim_results[0]
    assert result.status == "reproduced"
    assert result.observed == 0.91


def test_run_reproduction_pattern_claim_stdout_drifted_is_diverged_with_message(tmp_path):
    executor = _fake_executor(0, results=None, output="Final AUC: 0.5\n")
    claims = [
        Claim(
            id="auc",
            value=0.91,
            tolerance=0.05,
            locator=PatternLocator(None, r"Final AUC: ([0-9.]+)"),
        )
    ]
    record = _run(tmp_path, claims, executor)
    result = record.claim_results[0]
    assert result.status == "diverged"
    assert result.observed == 0.5
    assert "0.5" in result.message
    assert "0.91" in result.message
    assert result.delta is not None


def test_run_reproduction_pattern_claim_stdout_near_value_is_within_tolerance(tmp_path):
    executor = _fake_executor(0, results=None, output="Final AUC: 0.9\n")
    claims = [
        Claim(
            id="auc",
            value=0.91,
            tolerance=0.05,
            locator=PatternLocator(None, r"Final AUC: ([0-9.]+)"),
        )
    ]
    record = _run(tmp_path, claims, executor)
    result = record.claim_results[0]
    assert result.status == "within_tolerance"
    assert result.observed == 0.9


def test_run_reproduction_pattern_claim_file_matching_is_reproduced(tmp_path):
    _write_log(tmp_path, "logs/train.log", "epoch 1\nFinal AUC: 0.91\ndone\n")
    claims = [
        Claim(
            id="auc",
            value=0.91,
            tolerance=0.05,
            locator=PatternLocator("logs/train.log", r"Final AUC: ([0-9.]+)"),
        )
    ]
    record = _run(tmp_path, claims, _noop_executor())
    result = record.claim_results[0]
    assert result.status == "reproduced"
    assert result.observed == 0.91


def test_run_reproduction_pattern_claim_missing_file_is_unverified(tmp_path):
    claims = [
        Claim(
            id="auc",
            value=0.91,
            tolerance=0.05,
            locator=PatternLocator("logs/train.log", r"Final AUC: ([0-9.]+)"),
        )
    ]
    record = _run(tmp_path, claims, _noop_executor())
    result = record.claim_results[0]
    assert result.status == "unverified"
    assert result.observed is None
    assert "logs/train.log" in result.message


def test_run_reproduction_pattern_claim_directory_from_is_unverified(tmp_path):
    (tmp_path / "logs").mkdir()
    claims = [
        Claim(
            id="auc",
            value=0.91,
            tolerance=0.05,
            locator=PatternLocator("logs", r"Final AUC: ([0-9.]+)"),
        )
    ]
    record = _run(tmp_path, claims, _noop_executor())
    result = record.claim_results[0]
    assert result.status == "unverified"
    assert result.observed is None


def test_run_reproduction_pattern_claim_non_utf8_file_is_unverified(tmp_path):
    p = tmp_path / "logs" / "train.log"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"\xff\xfe\x00Final AUC: 0.91\n")
    claims = [
        Claim(
            id="auc",
            value=0.91,
            tolerance=0.05,
            locator=PatternLocator("logs/train.log", r"Final AUC: ([0-9.]+)"),
        )
    ]
    record = _run(tmp_path, claims, _noop_executor())
    result = record.claim_results[0]
    assert result.status == "unverified"
    assert result.observed is None


def test_run_reproduction_pattern_claim_zero_matches_is_unverified(tmp_path):
    executor = _fake_executor(0, results=None, output="nothing to see here\n")
    claims = [
        Claim(
            id="auc",
            value=0.91,
            tolerance=0.05,
            locator=PatternLocator(None, r"Final AUC: ([0-9.]+)"),
        )
    ]
    record = _run(tmp_path, claims, executor)
    result = record.claim_results[0]
    assert result.status == "unverified"
    assert result.observed is None
    assert "0" in result.message


def test_run_reproduction_pattern_claim_many_matches_is_unverified(tmp_path):
    executor = _fake_executor(
        0,
        results=None,
        output="Final AUC: 0.11\nFinal AUC: 0.22\nFinal AUC: 0.33\n",
    )
    claims = [
        Claim(
            id="auc",
            value=0.91,
            tolerance=0.05,
            locator=PatternLocator(None, r"Final AUC: ([0-9.]+)"),
        )
    ]
    record = _run(tmp_path, claims, executor)
    result = record.claim_results[0]
    assert result.status == "unverified"
    assert result.observed is None
    assert "3" in result.message


def test_run_reproduction_pattern_claim_unparseable_capture_is_unverified(tmp_path):
    executor = _fake_executor(0, results=None, output="Final AUC: NA\n")
    claims = [
        Claim(
            id="auc",
            value=0.91,
            tolerance=0.05,
            locator=PatternLocator(None, r"Final AUC: (\S+)"),
        )
    ]
    record = _run(tmp_path, claims, executor)
    result = record.claim_results[0]
    assert result.status == "unverified"
    assert result.observed is None
    assert "NA" in result.message


def test_run_reproduction_pattern_claim_non_finite_capture_is_unverified(tmp_path):
    executor = _fake_executor(0, results=None, output="Final AUC: inf\n")
    claims = [
        Claim(
            id="auc",
            value=0.91,
            tolerance=0.05,
            locator=PatternLocator(None, r"Final AUC: (\S+)"),
        )
    ]
    record = _run(tmp_path, claims, executor)
    result = record.claim_results[0]
    assert result.status == "unverified"
    assert result.observed is None


def test_run_reproduction_pattern_claim_numeric_string_capture_is_the_observed_value(tmp_path):
    # Deliberate divergence from the JSON locator rule (and identical to the
    # table rule): a regex capture is a string by construction, so a
    # numeric-looking string is the NORMAL valid case and must classify.
    _write_log(tmp_path, "logs/train.log", "count = 30.4\n")
    claims = [
        Claim(
            id="count",
            value=30.4,
            tolerance=0.05,
            locator=PatternLocator("logs/train.log", r"count = (\S+)"),
        )
    ]
    record = _run(tmp_path, claims, _noop_executor())
    result = record.claim_results[0]
    assert result.status == "reproduced"
    assert result.observed == 30.4


def test_run_reproduction_pattern_claim_stdout_reads_the_retried_run_output(tmp_path):
    # PRD M5: the observers are closures over `run_output`, and they are only
    # CALLED after the retry rebinds it -- so a stdout pattern claim binds the
    # SECOND run's output, not the failed first one.
    executor = _ScriptedExecutor(
        [(1, "No module named 'numpy'"), (0, "Final AUC: 0.91\n")]
    )
    installer = _ScriptedInstaller(0)
    claims = [
        Claim(
            id="auc",
            value=0.91,
            tolerance=0.05,
            locator=PatternLocator(None, r"Final AUC: ([0-9.]+)"),
        )
    ]
    record = _run(
        tmp_path, claims, executor, allow_install=True, installer=installer
    )
    assert executor.calls == 2
    result = record.claim_results[0]
    assert result.status == "reproduced"
    assert result.observed == 0.91


def test_run_reproduction_pattern_claim_escaping_repo_is_unverified_and_not_read(
    tmp_path, monkeypatch
):
    outside_dir = tmp_path.parent / "outside_pattern_secret"
    outside_dir.mkdir(exist_ok=True)
    secret_file = outside_dir / "secret.log"
    secret_file.write_text("Final AUC: 0.91\n")

    calls = _spy_read_text(monkeypatch)

    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    claims = [
        Claim(
            id="auc",
            value=0.91,
            tolerance=0.05,
            locator=PatternLocator(
                "../outside_pattern_secret/secret.log", r"Final AUC: ([0-9.]+)"
            ),
        )
    ]
    record = run_reproduction(
        repo=str(repo_dir),
        run_command="echo run",
        claims=claims,
        executor=_noop_executor(),
        claims_sha256="a" * 64,
        created_at="2026-07-18T00:00:00Z",
        reproduce_id="rp_1",
        run_started_at=_RUN_START,
    )
    result = record.claim_results[0]
    assert result.status == "unverified"
    assert result.observed is None
    assert "escapes the repo" in result.message
    assert secret_file.resolve() not in [c.resolve() for c in calls]


def test_run_reproduction_pattern_claim_stdout_never_touches_the_filesystem(
    tmp_path, monkeypatch
):
    calls = _spy_read_text(monkeypatch)
    executor = _fake_executor(0, results=None, output="Final AUC: 0.91\n")
    claims = [
        Claim(
            id="auc",
            value=0.91,
            tolerance=0.05,
            locator=PatternLocator(None, r"Final AUC: ([0-9.]+)"),
        )
    ]
    record = _run(tmp_path, claims, executor)
    assert record.claim_results[0].status == "reproduced"
    assert calls == []


def test_run_reproduction_pattern_claim_same_file_read_once(tmp_path, monkeypatch):
    _write_log(tmp_path, "logs/train.log", "Final AUC: 0.91\nFinal ACC: 0.8\n")
    calls = _spy_read_text(monkeypatch)
    log_path = (tmp_path / "logs" / "train.log").resolve()
    claims = [
        Claim(
            id="auc",
            value=0.91,
            tolerance=0.05,
            locator=PatternLocator("logs/train.log", r"Final AUC: ([0-9.]+)"),
        ),
        Claim(
            id="acc",
            value=0.8,
            tolerance=0.05,
            locator=PatternLocator("logs/train.log", r"Final ACC: ([0-9.]+)"),
        ),
    ]
    record = _run(tmp_path, claims, _noop_executor())
    by_id = {r.id: r for r in record.claim_results}
    assert by_id["auc"].status == "reproduced"
    assert by_id["acc"].status == "reproduced"
    assert [c.resolve() for c in calls].count(log_path) == 1


def test_run_reproduction_pattern_claim_oversized_file_is_unverified_and_not_read(
    tmp_path, monkeypatch
):
    # The cap is shrunk rather than writing a real 8 MiB fixture; the guard
    # reads the module global at call time, so this exercises the real branch.
    _write_log(tmp_path, "logs/train.log", "Final AUC: 0.91\n" * 20)
    monkeypatch.setattr(reproduce_module, "_MAX_MATCH_BYTES", 16)
    calls = _spy_read_text(monkeypatch)
    log_path = (tmp_path / "logs" / "train.log").resolve()
    claims = [
        Claim(
            id="auc",
            value=0.91,
            tolerance=0.05,
            locator=PatternLocator("logs/train.log", r"Final AUC: ([0-9.]+)"),
        )
    ]
    record = _run(tmp_path, claims, _noop_executor())
    result = record.claim_results[0]
    assert result.status == "unverified"
    assert result.observed is None
    assert "16" in result.message
    assert log_path not in [c.resolve() for c in calls]


def test_run_reproduction_pattern_claim_nonzero_exit_is_unverified(tmp_path):
    _write_log(tmp_path, "logs/train.log", "Final AUC: 0.91\n")
    claims = [
        Claim(
            id="auc",
            value=0.91,
            tolerance=0.05,
            locator=PatternLocator("logs/train.log", r"Final AUC: ([0-9.]+)"),
        ),
        Claim(
            id="auc_stdout",
            value=0.91,
            tolerance=0.05,
            locator=PatternLocator(None, r"Final AUC: ([0-9.]+)"),
        ),
    ]
    record = _run(tmp_path, claims, _noop_executor(exit_code=1))
    assert all(r.status == "unverified" for r in record.claim_results)
    assert all(r.observed is None for r in record.claim_results)
    assert "exit 1" in record.claim_results[0].message


def test_run_reproduction_pattern_claim_never_reaches_the_json_observer(tmp_path):
    # PRD R6: the dispatch head must be an explicit isinstance chain. A
    # PatternLocator routed into the JSON reader would raise AttributeError on
    # the missing `.path`; the failure must be the pattern-shaped message.
    _write_log(tmp_path, "logs/train.log", "no metric here\n")
    claims = [
        Claim(
            id="auc",
            value=0.91,
            tolerance=0.05,
            locator=PatternLocator("logs/train.log", r"Final AUC: ([0-9.]+)"),
        )
    ]
    record = _run(tmp_path, claims, _noop_executor())
    result = record.claim_results[0]
    assert result.status == "unverified"
    assert "locator pattern" in result.message
    assert "not valid JSON" not in result.message


def test_run_reproduction_mixed_pattern_table_json_and_flat_claims_resolve_independently(
    tmp_path,
):
    _write_located(tmp_path, "out/summary.json", {"model": {"auc": 0.9}})
    _write_tsv(tmp_path, "out/de.tsv", [_DE_HEADER, ["ENSG1", "-2.31", "0.001"]])
    _write_log(tmp_path, "logs/train.log", "Final F1: 0.77\n")
    pattern_file_claim = Claim(
        id="f1",
        value=0.77,
        tolerance=0.05,
        locator=PatternLocator("logs/train.log", r"Final F1: ([0-9.]+)"),
    )
    pattern_stdout_claim = Claim(
        id="loss",
        value=0.25,
        tolerance=0.05,
        locator=PatternLocator(None, r"Final loss: ([0-9.]+)"),
    )
    table_claim = Claim(
        id="log2fc",
        value=-2.31,
        tolerance=0.05,
        locator=TableLocator("out/de.tsv", "log2FoldChange", 0, "\t", True),
    )
    json_claim = Claim(
        id="auc", value=0.9, tolerance=0.05, locator=Locator("out/summary.json", "$.model.auc")
    )
    flat_claim = Claim(id="accuracy", value=0.8, tolerance=0.05)
    executor = _fake_executor(0, {"accuracy": 0.8}, output="Final loss: 0.25\n")
    record = _run(
        tmp_path,
        [pattern_file_claim, pattern_stdout_claim, table_claim, json_claim, flat_claim],
        executor,
    )
    by_id = {r.id: r for r in record.claim_results}
    assert by_id["f1"].status == "reproduced"
    assert by_id["loss"].status == "reproduced"
    assert by_id["log2fc"].status == "reproduced"
    assert by_id["auc"].status == "reproduced"
    assert by_id["accuracy"].status == "reproduced"


# ---------------------------------------------------------------------------
# run_reproduction() -- NotebookLocator (slice 5)
# ---------------------------------------------------------------------------


def _notebook_doc(output_text: str, source: str = "print(auc)\n") -> dict:
    """A one-code-cell notebook whose single stdout stream prints
    `output_text`; the cell `source` is `source`."""
    return {
        "cells": [
            {
                "cell_type": "code",
                "source": [source],
                "outputs": [
                    {"output_type": "stream", "name": "stdout", "text": [output_text]}
                ],
            }
        ]
    }


def _write_notebook(tmp_path: Path, rel: str, doc: object, mtime: float) -> Path:
    """Write `doc` (dict -> JSON, str -> verbatim) to `repo/rel` and stamp its
    mtime to `mtime` so the freshness guard is deterministic."""
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(doc if isinstance(doc, str) else json.dumps(doc))
    os.utime(p, (mtime, mtime))
    return p


def _nb_claim(value: float, cell, source: str = "out.ipynb", pattern: str = r"AUC: ([0-9.]+)"):
    return Claim(
        id="auc",
        value=value,
        tolerance=0.05,
        locator=NotebookLocator(source=source, cell=cell, pattern=pattern),
    )


def test_run_reproduction_notebook_fresh_matching_is_reproduced(tmp_path):
    _write_notebook(tmp_path, "out.ipynb", _notebook_doc("AUC: 0.91\n"), _RUN_START)
    record = _run(
        tmp_path, [_nb_claim(0.91, 0)], _noop_executor(), run_started_at=_RUN_START
    )
    result = record.claim_results[0]
    assert result.status == "reproduced"
    assert result.observed == 0.91


def test_run_reproduction_notebook_fresh_near_value_is_within_tolerance(tmp_path):
    _write_notebook(tmp_path, "out.ipynb", _notebook_doc("AUC: 0.9\n"), _RUN_START + 5)
    record = _run(
        tmp_path, [_nb_claim(0.91, 0)], _noop_executor(), run_started_at=_RUN_START
    )
    result = record.claim_results[0]
    assert result.status == "within_tolerance"
    assert result.observed == 0.9


def test_run_reproduction_notebook_fresh_drifted_is_diverged_with_message(tmp_path):
    _write_notebook(tmp_path, "out.ipynb", _notebook_doc("AUC: 0.5\n"), _RUN_START)
    record = _run(
        tmp_path, [_nb_claim(0.91, 0)], _noop_executor(), run_started_at=_RUN_START
    )
    result = record.claim_results[0]
    assert result.status == "diverged"
    assert result.observed == 0.5
    assert "0.5" in result.message
    assert "0.91" in result.message


def test_run_reproduction_notebook_stale_exact_match_is_unverified(tmp_path):
    # THE headline test of the whole slice: a notebook the run did NOT rewrite
    # (mtime predates run start) is UNVERIFIED even when its stored output
    # matches the claim exactly -- an author's committed notebook must never
    # produce a false REPRODUCED.
    _write_notebook(tmp_path, "out.ipynb", _notebook_doc("AUC: 0.91\n"), _RUN_START - 10)
    record = _run(
        tmp_path, [_nb_claim(0.91, 0)], _noop_executor(), run_started_at=_RUN_START
    )
    result = record.claim_results[0]
    assert result.status == "unverified"
    assert result.observed is None
    assert "rewritten" in result.message
    assert "run start" in result.message


def test_run_reproduction_notebook_missing_is_unverified(tmp_path):
    record = _run(
        tmp_path, [_nb_claim(0.91, 0)], _noop_executor(), run_started_at=_RUN_START
    )
    result = record.claim_results[0]
    assert result.status == "unverified"
    assert result.observed is None
    assert "out.ipynb" in result.message


def test_run_reproduction_notebook_oversized_is_unverified_naming_size(tmp_path, monkeypatch):
    monkeypatch.setattr(reproduce_module, "_MAX_MATCH_BYTES", 10)
    p = _write_notebook(tmp_path, "out.ipynb", _notebook_doc("AUC: 0.91\n"), _RUN_START)
    size = p.stat().st_size
    assert size > 10
    record = _run(
        tmp_path, [_nb_claim(0.91, 0)], _noop_executor(), run_started_at=_RUN_START
    )
    result = record.claim_results[0]
    assert result.status == "unverified"
    assert result.observed is None
    assert str(size) in result.message


def test_run_reproduction_notebook_non_json_is_unverified(tmp_path):
    _write_notebook(tmp_path, "out.ipynb", "{not json", _RUN_START)
    record = _run(
        tmp_path, [_nb_claim(0.91, 0)], _noop_executor(), run_started_at=_RUN_START
    )
    result = record.claim_results[0]
    assert result.status == "unverified"
    assert result.observed is None
    assert "not valid JSON" in result.message


def test_run_reproduction_notebook_unresolvable_cell_is_unverified(tmp_path):
    _write_notebook(tmp_path, "out.ipynb", _notebook_doc("AUC: 0.91\n"), _RUN_START)
    # cell index 5 is out of range for the single-cell notebook.
    record = _run(
        tmp_path, [_nb_claim(0.91, 5)], _noop_executor(), run_started_at=_RUN_START
    )
    result = record.claim_results[0]
    assert result.status == "unverified"
    assert result.observed is None
    assert "did not resolve" in result.message
    assert "out of range" in result.message


def test_run_reproduction_notebook_unresolvable_pattern_is_unverified(tmp_path):
    _write_notebook(tmp_path, "out.ipynb", _notebook_doc("AUC: 0.91\n"), _RUN_START)
    claim = _nb_claim(0.91, 0, pattern=r"F1: ([0-9.]+)")  # never matches
    record = _run(tmp_path, [claim], _noop_executor(), run_started_at=_RUN_START)
    result = record.claim_results[0]
    assert result.status == "unverified"
    assert result.observed is None
    assert "did not resolve" in result.message


def test_run_reproduction_notebook_claim_without_run_started_at_raises(tmp_path):
    # Programming error, NOT a silent UNVERIFIED: dispatching a notebook claim
    # with run_started_at=None is a non-bypassable guard that raises loudly.
    # `_run` now defaults run_started_at, so None must be passed explicitly
    # here to still exercise the raise.
    _write_notebook(tmp_path, "out.ipynb", _notebook_doc("AUC: 0.91\n"), _RUN_START)
    with pytest.raises(ValueError):
        _run(tmp_path, [_nb_claim(0.91, 0)], _noop_executor(), run_started_at=None)


def test_run_reproduction_notebook_allow_install_uses_retry_written_notebook(tmp_path):
    # M6a: run_started_at is stamped ONCE (here, before the first run) and not
    # re-stamped on the --allow-install retry. The retry writes a fresh
    # notebook, whose mtime is well after our injected run start, so it
    # resolves.
    run_started = 1.0  # any real file written now has a far-later mtime

    def executor(argv, repo):
        if executor.calls == 0:
            executor.calls += 1
            return 1, "No module named 'numpy'"
        executor.calls += 1
        _write_notebook(Path(repo), "out.ipynb", _notebook_doc("AUC: 0.91\n"), _now_mtime())
        return 0, ""

    executor.calls = 0
    installer = _ScriptedInstaller(0)
    record = _run(
        tmp_path,
        [_nb_claim(0.91, 0)],
        executor,
        allow_install=True,
        installer=installer,
        run_started_at=run_started,
    )
    assert executor.calls == 2
    result = record.claim_results[0]
    assert result.status == "reproduced"
    assert result.observed == 0.91


def _now_mtime() -> float:
    import time

    return time.time()
