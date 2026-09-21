"""Tests for the printed-precision equality core of locator matching
(match-and-propose aspect, Phase 1): `MatchOutcome`'s pinned frozen shape,
`_printed_precision` (repr-derived decimal places, the scientific-notation
exact-compare sentinel, the 12-place clamp), and `_value_matches` (the raw and
pct-scale rules, exact equality for integer-valued and scientific-notation
claims, the never-matches rules for non-finite values).

No matching logic is exercised here (Phase 2): `match_claims` and
`sidecar_text` are pinned only as callable public names so the module shape is
locked before any behavior lands.
"""

from dataclasses import FrozenInstanceError, fields
from typing import Literal, get_type_hints

import pytest

from contig.verification.locator_match import (
    MatchOutcome,
    _EXACT_COMPARE,
    _printed_precision,
    _value_matches,
    match_claims,
    sidecar_text,
)
from contig.verification.reproduce import Locator, TableLocator


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