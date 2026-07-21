"""Boundary tests for C8 slice 4 phase 2: the pure regex capture resolver
`resolve_match`.

Strict TDD: this file is written before `resolve_match` exists in
src/contig/verification/reproduce.py.

Mirrors tests/test_reproduce_tsv_locator.py's structure (the pure TSV/CSV cell
resolver tests): `resolve_match` must never raise -- any oversized text,
uncompilable pattern, ambiguous match count, or non-participating capture group
returns `(None, reason)` rather than raising. On success it returns the RAW
captured string; parsing it to a float is the caller's job.
"""

from __future__ import annotations

from contig.verification.reproduce import _MAX_MATCH_BYTES, resolve_match

# ---------------------------------------------------------------------------
# resolve_match -- happy paths (capture selection, M3)
# ---------------------------------------------------------------------------


def test_resolve_match_one_match_one_group_returns_group_one():
    captured, reason = resolve_match("Final AUC: 0.91\n", r"Final AUC: ([\d.]+)")
    assert captured == "0.91"
    assert reason == ""


def test_resolve_match_one_match_no_groups_returns_whole_match():
    captured, reason = resolve_match("Final AUC: 0.91\n", r"0\.\d+")
    assert captured == "0.91"
    assert reason == ""


def test_resolve_match_named_group_behaves_as_group_one():
    captured, reason = resolve_match("Final AUC: 0.91\n", r"AUC: (?P<v>[\d.]+)")
    assert captured == "0.91"
    assert reason == ""


def test_resolve_match_inline_ignorecase_flag_is_honored():
    captured, reason = resolve_match("Final AUC: 0.91\n", r"(?i)final auc: ([\d.]+)")
    assert captured == "0.91"
    assert reason == ""


def test_resolve_match_inline_multiline_flag_is_honored():
    text = "header line\nAUC=0.91\ntrailer line\n"
    captured, reason = resolve_match(text, r"(?m)^AUC=([\d.]+)$")
    assert captured == "0.91"
    assert reason == ""


def test_resolve_match_multi_group_pattern_returns_group_one_only():
    captured, reason = resolve_match("auc=0.91 f1=0.73", r"auc=([\d.]+) f1=([\d.]+)")
    assert captured == "0.91"
    assert reason == ""


def test_resolve_match_returns_raw_string_not_a_float():
    captured, _reason = resolve_match("Final AUC: 0.910", r"AUC: ([\d.]+)")
    assert captured == "0.910"
    assert isinstance(captured, str)


# ---------------------------------------------------------------------------
# resolve_match -- strict ambiguity (0 or >1 matches, never an arbitrary pick)
# ---------------------------------------------------------------------------


def test_resolve_match_zero_matches_returns_none_with_count():
    captured, reason = resolve_match("nothing to see here", r"AUC=([\d.]+)")
    assert captured is None
    assert "0" in reason


def test_resolve_match_three_matches_returns_none_with_count():
    text = "AUC=0.1\nAUC=0.2\nAUC=0.3\n"
    captured, reason = resolve_match(text, r"AUC=([\d.]+)")
    assert captured is None
    assert "3" in reason


# ---------------------------------------------------------------------------
# resolve_match -- non-participating capture group (the one crashing shape)
# ---------------------------------------------------------------------------


def test_resolve_match_non_participating_group_returns_none_not_type_error():
    # Exactly one match, but group 1 did not participate -> m.group(1) is None,
    # and float(None) would raise TypeError downstream.
    captured, reason = resolve_match("z", r"(?:x)?(y)?z")
    assert captured is None
    assert reason != ""


def test_resolve_match_non_participating_group_in_alternation():
    captured, reason = resolve_match("AUC=0.9", r"AUC=(?:(old)|([\d.]+))")
    assert captured is None
    assert "participate" in reason


def test_resolve_match_optional_alternation_pattern_never_raises():
    # The PRD's illustrative shape. Note this pattern actually matches THREE
    # times (the `(old)?` branch matches empty at every position), so it
    # degrades through the ambiguity branch -- either way, no TypeError.
    captured, reason = resolve_match("AUC=0.9", r"(old)?|AUC=([\d.]+)")
    assert captured is None
    assert isinstance(reason, str)
    assert reason != ""


# ---------------------------------------------------------------------------
# resolve_match -- size bound (M6) and uncompilable patterns
# ---------------------------------------------------------------------------


def test_resolve_match_oversized_text_returns_none_naming_the_size():
    text = "x" * (_MAX_MATCH_BYTES + 1)
    captured, reason = resolve_match(text, r"(x)")
    assert captured is None
    assert str(len(text)) in reason
    assert str(_MAX_MATCH_BYTES) in reason


def test_resolve_match_size_bound_is_checked_before_compiling():
    # An uncompilable pattern paired with oversized text must report the SIZE,
    # proving the bound is applied before any compile or scan attempt.
    text = "x" * (_MAX_MATCH_BYTES + 1)
    captured, reason = resolve_match(text, "(")
    assert captured is None
    assert str(len(text)) in reason


def test_resolve_match_at_the_size_bound_is_still_scanned():
    text = "y" * (_MAX_MATCH_BYTES - 1) + "z"
    captured, reason = resolve_match(text, r"z")
    assert captured == "z"
    assert reason == ""


def test_resolve_match_uncompilable_pattern_returns_none_never_raises():
    captured, reason = resolve_match("Final AUC: 0.91", "(")
    assert captured is None
    assert reason != ""


# ---------------------------------------------------------------------------
# resolve_match -- never raises, on anything
# ---------------------------------------------------------------------------


def test_resolve_match_never_raises_on_wild_inputs():
    wild_patterns = [
        "",
        "(",
        "*",
        "(?P<>)",
        "a{100000,}",
        "[z-a]",
        "\\",
        "(?#",
    ]
    wild_texts = [
        "",
        "abc",
        "header line\nAUC=0.91\nf1 = 0.73\n\ttrailing\n",
    ]
    for pattern in wild_patterns:
        for text in wild_texts:
            result = resolve_match(text, pattern)
            assert isinstance(result, tuple)
            assert len(result) == 2
            captured, reason = result
            assert captured is None or isinstance(captured, str)
            assert isinstance(reason, str)
