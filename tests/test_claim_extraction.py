"""Tests for the deterministic paper-claim extractor core (aspect
`extractor-core` of reproduce-paper-claims).

Strict TDD: written before `src/contig/verification/claim_extraction.py`
exists. `extract_claims` must never raise -- any malformed / empty / non-str
input degrades to `[]`, mirroring the never-raises resolvers in
`verification/reproduce.py` (see `tests/test_reproduce_locator.py`).
"""

from __future__ import annotations

import dataclasses

import pytest

from contig.verification.claim_extraction import (
    ExtractedClaim,
    _METRIC_VOCAB,
    _parse_number,
    _slug,
    extract_claims,
)


def _triples(text: str) -> set[tuple[str, float, str | None]]:
    """(metric_slug, value, unit) set for a text -- the corpus-labeling shape."""
    return {(_slug(c.metric), c.value, c.unit) for c in extract_claims(text)}


# ---------------------------------------------------------------------------
# Phase 1: ExtractedClaim model + extract_claims skeleton
# ---------------------------------------------------------------------------


def test_extracted_claim_fields_and_defaults():
    claim = ExtractedClaim(id="auc", value=0.91, metric="AUC")
    assert claim.id == "auc"
    assert claim.value == 0.91
    assert claim.metric == "AUC"
    # defaults
    assert claim.tolerance == 0.1
    assert claim.unit is None
    assert claim.source_text == ""
    assert claim.origin == "heuristic"


def test_extracted_claim_is_frozen():
    claim = ExtractedClaim(id="auc", value=0.91, metric="AUC")
    with pytest.raises(dataclasses.FrozenInstanceError):
        claim.value = 0.5  # type: ignore[misc]


def test_extract_claims_empty_string_returns_empty_list():
    assert extract_claims("") == []


# ---------------------------------------------------------------------------
# Phase 2: the deterministic matcher
# ---------------------------------------------------------------------------


def test_metric_vocab_is_non_empty_lowercase_seed():
    assert _METRIC_VOCAB  # non-empty
    assert all(m == m.lower() for m in _METRIC_VOCAB)
    # a sampling of the spec's enumerated seed is present
    for m in ("auc", "accuracy", "f1", "pearson", "correlation", "log2 fold change"):
        assert m in _METRIC_VOCAB


def test_slug_rules():
    assert _slug("AUC") == "auc"
    assert _slug("log2 fold change") == "log2_fold_change"
    assert _slug("F1 score") == "f1_score"
    assert _slug("r-squared") == "r_squared"
    assert _slug("r2") == "r2"
    # R-squared as the superscript form: non-ascii-alnum collapses to `_` then
    # strips -> "r" (pinned rule; documented in the module).
    assert _slug("R²") == "r"


def test_parse_number_plain_and_percent_and_sci_and_nonfinite():
    assert _parse_number("0.91") == (0.91, None)
    assert _parse_number("-2.3") == (-2.3, None)
    assert _parse_number("87%") == (87.0, "%")
    val, unit = _parse_number("1.2e-3")
    assert val == pytest.approx(0.0012)
    assert unit is None
    # a value that overflows to a non-finite float is skipped, never emitted
    assert _parse_number("1e400") == (None, None)


def test_canonical_positive_auc():
    claims = extract_claims("The model achieved an AUC of 0.91 on the test set.")
    assert len(claims) == 1
    (c,) = claims
    assert _slug(c.metric) == "auc"
    assert c.value == 0.91
    assert c.unit is None
    assert c.id == "auc"


def test_canonical_positive_accuracy_percent():
    claims = extract_claims("Overall accuracy of 87% was reported.")
    assert len(claims) == 1
    (c,) = claims
    assert _slug(c.metric) == "accuracy"
    assert c.value == 87.0  # raw number, never divided by 100
    assert c.unit == "%"


def test_canonical_positive_f1_equals():
    assert _triples("We report F1 = 0.83 for this task.") == {("f1", 0.83, None)}


def test_canonical_positive_log2_fold_change_negative():
    assert _triples("A log2 fold change of -2.3 was observed.") == {
        ("log2_fold_change", -2.3, None)
    }


def test_canonical_positive_pearson_correlation():
    # "Pearson correlation of 0.76": the nearer vocabulary metric owns the
    # number (precision rule -- a metric whose gap to the number contains
    # another metric is skipped), so exactly one claim is emitted.
    assert _triples("The Pearson correlation of 0.76 was significant.") == {
        ("correlation", 0.76, None)
    }


def test_inequality_yields_no_claim():
    # No connective before the number -> no claim.
    assert extract_claims("We found accuracy > 0.9 in all runs.") == []
    # p is not a vocabulary metric.
    assert extract_claims("The result was significant (p < 0.001).") == []
    # Connective present but an inequality immediately precedes the number ->
    # the inequality-skip branch fires.
    assert extract_claims("Sensitivity of < 0.9 was never seen.") == []
    assert extract_claims("Specificity was >= 0.95 throughout.") == []


def test_source_text_contains_metric_and_number():
    (c,) = extract_claims("First sentence. The AUC of 0.91 held up. Then more.")
    assert "AUC" in c.source_text
    assert "0.91" in c.source_text
    # the sentence is isolated, not the whole blob
    assert "First sentence" not in c.source_text
    assert "Then more" not in c.source_text


def test_two_values_same_metric_get_uniquified_ids():
    claims = extract_claims("AUC of 0.91 on cohort A; AUC of 0.85 on cohort B.")
    assert [c.id for c in claims] == ["auc", "auc_2"]
    assert [c.value for c in claims] == [0.91, 0.85]


def test_ids_are_deterministic_across_runs():
    text = "AUC of 0.91 then AUC of 0.85 then accuracy of 0.7."
    first = [c.id for c in extract_claims(text)]
    second = [c.id for c in extract_claims(text)]
    assert first == second == ["auc", "auc_2", "accuracy"]


def test_dedup_same_metric_and_value_collapses_filewide():
    # Same (metric_slug, value) twice -> one claim; first source_text kept.
    claims = extract_claims(
        "AUC of 0.91 in the abstract. Later, AUC of 0.91 in the results."
    )
    assert len(claims) == 1
    assert "abstract" in claims[0].source_text


def test_distinct_metrics_sharing_a_value_are_two_claims():
    claims = extract_claims("AUC of 0.9 and accuracy of 0.9 were reported.")
    assert {(_slug(c.metric), c.value) for c in claims} == {
        ("auc", 0.9),
        ("accuracy", 0.9),
    }
    assert len({c.id for c in claims}) == 2
