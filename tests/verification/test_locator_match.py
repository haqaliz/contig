"""Tests for the locator matcher (match-and-propose aspect): Phase 1 pins the
printed-precision equality core (`MatchOutcome`'s frozen shape,
`_printed_precision`, `_value_matches`), Phase 2 pins the full matching rule
`match_claims` -- site grouping at (source, coordinate) granularity (M4), the
dual-scale exactly-one rule (M5), the M9 low-information refusal (deny-list +
integer significant-digit rule, short-circuiting before matching), and the
never-raises contract (M7). `sidecar_text` remains pinned only as a callable
public name (Phase 3).
"""

from dataclasses import FrozenInstanceError, fields
from typing import Literal, get_type_hints

import pytest

from contig.verification.locator_inference import Candidate
from contig.verification.locator_match import (
    MatchOutcome,
    _EXACT_COMPARE,
    _printed_precision,
    _significant_digits,
    _value_matches,
    match_claims,
    sidecar_text,
)
from contig.verification.reproduce import Claim, Locator, TableLocator


def test_module_exposes_pinned_public_surface():
    assert callable(match_claims)
    assert callable(sidecar_text)


def test_printed_precision_counts_digits_after_the_decimal_point():
    assert _printed_precision(0.9134) == 4
    assert _printed_precision(0.91) == 2
    assert _printed_precision(12.5) == 1


def test_printed_precision_of_int_valued_float_is_zero():
    assert _printed_precision(87.0) == 0


def test_printed_precision_of_scientific_notation_repr_is_exact_compare_sentinel():
    assert _printed_precision(1e-05) == _EXACT_COMPARE
    assert _printed_precision(1.5e-07) == _EXACT_COMPARE
    assert _EXACT_COMPARE < 0


def test_printed_precision_clamps_at_twelve_decimal_places():
    assert _printed_precision(0.123456789012345) == 12


def test_value_matches_float_claim_rounds_candidate_to_claim_precision():
    assert _value_matches(0.9134, 0.91, "raw", 2) is True
    assert _value_matches(0.9154, 0.91, "raw", 2) is False


def test_value_matches_int_valued_claim_requires_exact_equality():
    assert _value_matches(875.6, 876, "raw", 0) is False
    assert _value_matches(876.0, 876, "raw", 0) is True


def test_value_matches_int_candidate_matches_float_claim():
    assert _value_matches(7, 7.0, "raw", 0) is True
    assert _value_matches(7.0, 7, "raw", 0) is True


def test_value_matches_exact_compare_precision_requires_exact_equality():
    assert _value_matches(1e-05, 1e-05, "raw", _EXACT_COMPARE) is True
    assert _value_matches(1.2e-05, 1e-05, "raw", _EXACT_COMPARE) is False


def test_value_matches_pct_scale_divides_claim_value_by_100():
    assert _value_matches(0.87, 87, "pct", 0) is True
    assert _value_matches(0.0091, 0.91, "pct", 2) is True


def test_value_matches_pct_scale_rounding_misses_distant_candidate():
    assert _value_matches(0.8754, 87, "pct", 0) is False


def test_value_matches_pct_scale_int_valued_divided_claim_requires_exact_equality():
    assert _value_matches(876.0, 87600, "pct", 0) is True
    assert _value_matches(875.6, 87600, "pct", 0) is False


def test_value_matches_pct_scale_scientific_notation_compares_exactly():
    assert _value_matches(1e-06, 1e-04, "pct", _EXACT_COMPARE) is True
    assert _value_matches(1.5e-06, 1e-04, "pct", _EXACT_COMPARE) is False


def test_value_matches_non_finite_candidate_never_matches():
    assert _value_matches(float("nan"), 0.91, "raw", 2) is False
    assert _value_matches(float("inf"), 0.91, "raw", 2) is False
    assert _value_matches(float("-inf"), 0.91, "raw", 2) is False


def test_value_matches_non_finite_claim_never_matches_and_never_raises():
    assert _value_matches(0.91, float("nan"), "raw", 2) is False
    assert _value_matches(0.91, float("inf"), "raw", 2) is False


def test_match_outcome_is_frozen_with_pinned_fields():
    hints = get_type_hints(MatchOutcome)
    assert hints["claim_id"] is str
    assert hints["value"] is float
    assert hints["scale"] == Literal["raw", "pct"] | None
    assert hints["locator"] == Locator | TableLocator | None
    assert hints["site_count"] is int
    assert hints["reason"] == Literal[
        "bound", "ambiguous", "refused_low_information", "no_candidates"
    ]

    outcome = MatchOutcome(
        claim_id="auc",
        value=0.91,
        scale="raw",
        locator=Locator(source="results.json", path="auc"),
        site_count=1,
        reason="bound",
    )
    assert [f.name for f in fields(MatchOutcome)] == [
        "claim_id",
        "value",
        "scale",
        "locator",
        "site_count",
        "reason",
    ]
    assert (outcome.claim_id, outcome.value, outcome.scale, outcome.site_count) == (
        "auc",
        0.91,
        "raw",
        1,
    )
    assert outcome.locator == Locator(source="results.json", path="auc")
    with pytest.raises(FrozenInstanceError):
        outcome.site_count = 2


def test_single_json_candidate_match_binds_locator_fields_verbatim():
    candidate = Candidate(source="results.json", kind="json", value=0.9134, path="auc")
    claim = Claim(id="auc", value=0.91, tolerance=0.05)
    (outcome,) = match_claims([candidate], [claim])
    assert outcome.reason == "bound"
    assert outcome.scale == "raw"
    assert outcome.site_count == 1
    assert outcome.claim_id == "auc"
    assert outcome.value == 0.91
    assert outcome.locator == Locator(source="results.json", path="auc")
    assert outcome.locator.source == candidate.source
    assert outcome.locator.path == candidate.path


def test_single_table_candidate_header_mode_binds_complete_table_locator_without_delimiter():
    candidate = Candidate(
        source="out/de.tsv",
        kind="table",
        value=1.2,
        column="log2FoldChange",
        row=0,
        header=True,
    )
    claim = Claim(id="lfc", value=1.2, tolerance=0.05)
    (outcome,) = match_claims([candidate], [claim])
    assert outcome.reason == "bound"
    assert outcome.scale == "raw"
    assert outcome.site_count == 1
    assert outcome.locator == TableLocator(
        source="out/de.tsv",
        column="log2FoldChange",
        row=0,
        delimiter="",
        header=True,
    )
    assert outcome.locator.delimiter == ""


def test_headerless_table_candidate_match_binds():
    candidate = Candidate(
        source="out/counts.tsv",
        kind="table",
        value=876.0,
        column=2,
        row=41,
        header=False,
    )
    claim = Claim(id="count", value=876.0, tolerance=0.05)
    (outcome,) = match_claims([candidate], [claim])
    assert outcome.reason == "bound"
    assert outcome.scale == "raw"
    assert outcome.site_count == 1
    assert outcome.locator == TableLocator(
        source="out/counts.tsv", column=2, row=41, delimiter="", header=False
    )


def test_same_value_at_two_json_leaves_is_ambiguous():
    candidates = [
        Candidate(source="results.json", kind="json", value=0.9134, path="auc"),
        Candidate(source="results.json", kind="json", value=0.9134, path="f1"),
    ]
    claim = Claim(id="auc", value=0.91, tolerance=0.05)
    (outcome,) = match_claims(candidates, [claim])
    assert outcome.reason == "ambiguous"
    assert outcome.site_count == 2
    assert outcome.locator is None
    assert outcome.scale is None


def test_same_value_in_one_json_leaf_and_one_table_cell_is_ambiguous():
    candidates = [
        Candidate(source="results.json", kind="json", value=0.9134, path="auc"),
        Candidate(
            source="out/de.tsv",
            kind="table",
            value=0.9134,
            column="log2FoldChange",
            row=0,
            header=True,
        ),
    ]
    claim = Claim(id="auc", value=0.91, tolerance=0.05)
    (outcome,) = match_claims(candidates, [claim])
    assert outcome.reason == "ambiguous"
    assert outcome.site_count == 2
    assert outcome.locator is None
    assert outcome.scale is None


def test_same_value_in_two_table_cells_different_rows_is_ambiguous():
    candidates = [
        Candidate(
            source="out/de.tsv",
            kind="table",
            value=0.75,
            column="log2FoldChange",
            row=0,
            header=True,
        ),
        Candidate(
            source="out/de.tsv",
            kind="table",
            value=0.75,
            column="log2FoldChange",
            row=1,
            header=True,
        ),
    ]
    claim = Claim(id="lfc", value=0.75, tolerance=0.05)
    (outcome,) = match_claims(candidates, [claim])
    assert outcome.reason == "ambiguous"
    assert outcome.site_count == 2
    assert outcome.locator is None
    assert outcome.scale is None


def test_duplicate_table_rows_count_as_one_site_and_bind():
    candidates = [
        Candidate(
            source="out/de.tsv",
            kind="table",
            value=0.75,
            column="log2FoldChange",
            row=0,
            header=True,
        ),
        Candidate(
            source="out/de.tsv",
            kind="table",
            value=0.75,
            column="log2FoldChange",
            row=0,
            header=True,
        ),
    ]
    claim = Claim(id="lfc", value=0.75, tolerance=0.05)
    (outcome,) = match_claims(candidates, [claim])
    assert outcome.reason == "bound"
    assert outcome.site_count == 1
    assert outcome.scale == "raw"
    assert outcome.locator == TableLocator(
        source="out/de.tsv",
        column="log2FoldChange",
        row=0,
        delimiter="",
        header=True,
    )


def test_pct_scale_int_claim_binds_repo_value_divided_by_100():
    candidate = Candidate(
        source="out/de.tsv",
        kind="table",
        value=8.76,
        column="log2FoldChange",
        row=0,
        header=True,
    )
    claim = Claim(id="lfc", value=876.0, tolerance=0.05)
    (outcome,) = match_claims([candidate], [claim])
    assert outcome.reason == "bound"
    assert outcome.scale == "pct"
    assert outcome.site_count == 1
    assert outcome.locator == TableLocator(
        source="out/de.tsv",
        column="log2FoldChange",
        row=0,
        delimiter="",
        header=True,
    )


def test_pct_scale_float_claim_binds_repo_value_divided_by_100():
    candidate = Candidate(
        source="out/de.tsv",
        kind="table",
        value=0.0091,
        column="log2FoldChange",
        row=0,
        header=True,
    )
    claim = Claim(id="lfc", value=0.91, tolerance=0.05)
    (outcome,) = match_claims([candidate], [claim])
    assert outcome.reason == "bound"
    assert outcome.scale == "pct"
    assert outcome.site_count == 1


def test_raw_and_pct_both_match_at_different_sites_is_ambiguous():
    candidates = [
        Candidate(source="results.json", kind="json", value=0.91, path="auc"),
        Candidate(
            source="out/de.tsv",
            kind="table",
            value=0.0091,
            column="log2FoldChange",
            row=0,
            header=True,
        ),
    ]
    claim = Claim(id="auc", value=0.91, tolerance=0.05)
    (outcome,) = match_claims(candidates, [claim])
    assert outcome.reason == "ambiguous"
    assert outcome.site_count == 2
    assert outcome.locator is None
    assert outcome.scale is None


@pytest.mark.parametrize(
    "low", [0, 1, 0.5, 0.05, 100, 0.0, 1.0, 0.5, 0.05, 100.0]
)
def test_m9_deny_list_values_are_refused_even_with_a_matching_candidate(low):
    candidate = Candidate(source="results.json", kind="json", value=low, path="auc")
    claim = Claim(id="c", value=low, tolerance=0.05)
    (outcome,) = match_claims([candidate], [claim])
    assert outcome.reason == "refused_low_information"
    assert outcome.site_count == 0
    assert outcome.locator is None
    assert outcome.scale is None


def test_significant_digits_count_ignores_trailing_zeros():
    assert _significant_digits(87.0) == 2
    assert _significant_digits(870.0) == 2
    assert _significant_digits(876.0) == 3
    assert _significant_digits(1234.0) == 4
    assert _significant_digits(1000000.0) == 1


def test_m9_integer_significant_digit_rule_refuses_or_binds():
    candidates = [
        Candidate(source="r.json", kind="json", value=99.0, path="x"),
        Candidate(source="r.json", kind="json", value=870.0, path="y"),
        Candidate(source="r.json", kind="json", value=1234.0, path="z"),
        Candidate(source="r.json", kind="json", value=1000000.0, path="w"),
    ]
    claims = [
        Claim(id="c87", value=87.0, tolerance=0.05),
        Claim(id="c870", value=870.0, tolerance=0.05),
        Claim(id="c1234", value=1234.0, tolerance=0.05),
        Claim(id="c1m", value=1000000.0, tolerance=0.05),
    ]
    outcomes = match_claims(candidates, claims)
    assert outcomes[0].reason == "refused_low_information"
    assert outcomes[0].site_count == 0
    assert outcomes[1].reason == "refused_low_information"
    assert outcomes[2].reason == "bound"
    assert outcomes[2].locator.path == "z"
    assert outcomes[3].reason == "refused_low_information"


def test_m9_refusal_short_circuits_before_pct_matching():
    candidate = Candidate(
        source="out/de.tsv",
        kind="table",
        value=0.87,
        column="log2FoldChange",
        row=0,
        header=True,
    )
    claim = Claim(id="lfc", value=87.0, tolerance=0.05)
    (outcome,) = match_claims([candidate], [claim])
    assert outcome.reason == "refused_low_information"
    assert outcome.site_count == 0
    assert outcome.locator is None
    assert outcome.scale is None


def test_no_matches_is_no_candidates():
    candidates = [
        Candidate(source="a.json", kind="json", value=1.5, path="x"),
        Candidate(source="b.tsv", kind="table", value=0.75, column="c", row=0, header=True),
    ]
    claim = Claim(id="auc", value=0.9134, tolerance=0.05)
    (outcome,) = match_claims(candidates, [claim])
    assert outcome.reason == "no_candidates"
    assert outcome.site_count == 0
    assert outcome.locator is None
    assert outcome.scale is None


def test_non_finite_claim_value_is_no_candidates_never_raises():
    claims = [
        Claim(id="inf", value=float("inf"), tolerance=0.05),
        Claim(id="ninf", value=float("-inf"), tolerance=0.05),
        Claim(id="nan", value=float("nan"), tolerance=0.05),
    ]
    outcomes = match_claims([Candidate(source="a.json", kind="json", value=1.5, path="x")], claims)
    assert [o.reason for o in outcomes] == ["no_candidates", "no_candidates", "no_candidates"]
    assert [o.site_count for o in outcomes] == [0, 0, 0]


def test_empty_claims_returns_empty_list():
    candidate = Candidate(source="results.json", kind="json", value=0.9134, path="auc")
    assert match_claims([candidate], []) == []


def test_empty_candidates_yields_no_candidates_per_claim_in_order():
    claims = [
        Claim(id="a", value=0.9134, tolerance=0.05),
        Claim(id="b", value=0.75, tolerance=0.05),
    ]
    outcomes = match_claims([], claims)
    assert [o.claim_id for o in outcomes] == ["a", "b"]
    assert [o.reason for o in outcomes] == ["no_candidates", "no_candidates"]
    assert all(o.site_count == 0 and o.locator is None and o.scale is None for o in outcomes)


def test_malformed_candidates_are_skipped_without_raising():
    candidates = [
        Candidate(source="weird.json", kind="hologram", value=0.9134),
        Candidate(source="broken.json", kind="json", value=0.9134, path=None),
        Candidate(source="t1.tsv", kind="table", value=0.9134, column=None, row=0, header=True),
        Candidate(source="t2.tsv", kind="table", value=0.9134, column="x", row=None, header=True),
        Candidate(source="t3.tsv", kind="table", value=0.9134, column="x", row=0, header=None),
        Candidate(source="results.json", kind="json", value=0.91, path="auc"),
    ]
    claims = [
        Claim(id="a", value=0.91, tolerance=0.05),
        Claim(id="b", value=0.9134, tolerance=0.05),
    ]
    outcomes = match_claims(candidates, claims)
    assert outcomes[0].reason == "bound"
    assert outcomes[0].locator == Locator(source="results.json", path="auc")
    assert outcomes[1].reason == "no_candidates"


def test_claims_order_preserved_across_mixed_outcomes():
    candidates = [
        Candidate(source="results.json", kind="json", value=0.9134, path="auc"),
        Candidate(
            source="out/de.tsv",
            kind="table",
            value=0.75,
            column="log2FoldChange",
            row=0,
            header=True,
        ),
        Candidate(
            source="out/de.tsv",
            kind="table",
            value=0.75,
            column="log2FoldChange",
            row=1,
            header=True,
        ),
    ]
    claims = [
        Claim(id="bound_c", value=0.91, tolerance=0.05),
        Claim(id="amb_c", value=0.75, tolerance=0.05),
        Claim(id="ref_c", value=0.5, tolerance=0.05),
        Claim(id="none_c", value=0.42, tolerance=0.05),
    ]
    outcomes = match_claims(candidates, claims)
    assert [o.claim_id for o in outcomes] == ["bound_c", "amb_c", "ref_c", "none_c"]
    assert [o.reason for o in outcomes] == [
        "bound",
        "ambiguous",
        "refused_low_information",
        "no_candidates",
    ]