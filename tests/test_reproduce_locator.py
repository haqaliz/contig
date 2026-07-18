"""Boundary tests for C8 slice 1.5 phase 1: the pure dotted+[n] JSON path
walker `resolve_pointer` (and its tokenizer `_parse_path`).

Strict TDD: this file is written before `resolve_pointer`/`_parse_path` exist
in src/contig/verification/reproduce.py.

`resolve_pointer` must never raise -- any unresolved or malformed input
returns `None`.
"""

from __future__ import annotations

import json

from contig.verification.reproduce import resolve_pointer


# ---------------------------------------------------------------------------
# AC1: happy paths
# ---------------------------------------------------------------------------


def test_resolve_pointer_dotted_key_with_leading_dollar_dot():
    assert resolve_pointer({"model": {"auc": 0.9}}, "$.model.auc") == 0.9


def test_resolve_pointer_dict_then_list_index_then_key():
    assert resolve_pointer({"samples": [{"n": 5}]}, "samples[0].n") == 5


def test_resolve_pointer_top_level_list_index_then_key():
    assert resolve_pointer([{"name": "x"}], "[0].name") == "x"


def test_resolve_pointer_prefix_variants_are_equivalent_for_dict_root():
    data = {"model": {"auc": 0.9}}
    assert resolve_pointer(data, "$.model.auc") == 0.9
    assert resolve_pointer(data, "model.auc") == 0.9
    assert resolve_pointer(data, "$model.auc") == 0.9


def test_resolve_pointer_bare_top_level_key():
    assert resolve_pointer({"auc": 0.9}, "auc") == 0.9
    assert resolve_pointer({"auc": 0.9}, "$.auc") == 0.9
    assert resolve_pointer({"auc": 0.9}, "$auc") == 0.9


# ---------------------------------------------------------------------------
# AC2: malformed / miss cases -- always None, never raise
# ---------------------------------------------------------------------------


def test_resolve_pointer_missing_key_returns_none():
    assert resolve_pointer({"model": {"auc": 0.9}}, "model.missing") is None


def test_resolve_pointer_index_out_of_range_returns_none():
    assert resolve_pointer({"samples": [{"n": 5}]}, "samples[9].n") is None


def test_resolve_pointer_index_on_dict_returns_none():
    assert resolve_pointer({"model": {"auc": 0.9}}, "model[0]") is None


def test_resolve_pointer_key_on_list_returns_none():
    assert resolve_pointer({"samples": [{"n": 5}]}, "samples.n") is None


def test_resolve_pointer_double_dot_returns_none():
    assert resolve_pointer({"a": {"b": 1}}, "a..b") is None


def test_resolve_pointer_non_digit_index_returns_none():
    assert resolve_pointer({"a": [1, 2]}, "a[x]") is None


def test_resolve_pointer_unclosed_bracket_returns_none():
    assert resolve_pointer({"a": [1, 2]}, "a[") is None


def test_resolve_pointer_trailing_chars_after_bracket_returns_none():
    assert resolve_pointer({"a": [1, 2]}, "a[0]b") is None


def test_resolve_pointer_trailing_dot_returns_none():
    assert resolve_pointer({"a": {"b": 1}}, "a.") is None


def test_resolve_pointer_empty_string_returns_none():
    assert resolve_pointer({"a": 1}, "") is None


def test_resolve_pointer_dollar_only_returns_none():
    assert resolve_pointer({"a": 1}, "$") is None


def test_resolve_pointer_dollar_dot_only_returns_none():
    assert resolve_pointer({"a": 1}, "$.") is None


def test_resolve_pointer_null_target_returns_none():
    data = json.loads('{"a": {"b": null}}')
    assert resolve_pointer(data, "a.b") is None


def test_resolve_pointer_never_raises_on_wild_inputs():
    # A grab-bag of adversarial inputs -- must degrade to None, not raise.
    data = {"a": {"b": [1, 2, {"c": 3}]}}
    wild_exprs = [
        "a..b",
        "a[x]",
        "a[",
        "a[0]b",
        "a.",
        "",
        "$",
        "$.",
        "a[-1]",
        "a[ 0]",
        "a[0",
        "..",
        "[",
        "]",
        "a.b[0].c.",
        "a.b[99].c",
    ]
    for expr in wild_exprs:
        assert resolve_pointer(data, expr) is None
        assert resolve_pointer([1, 2, 3], expr) is None
        assert resolve_pointer("a string", expr) is None
        assert resolve_pointer(None, expr) is None
