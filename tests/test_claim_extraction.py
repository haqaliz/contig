"""Tests for the deterministic paper-claim extractor core (aspect
`extractor-core` of reproduce-paper-claims).

Strict TDD: written before `src/contig/verification/claim_extraction.py`
exists. `extract_claims` must never raise -- any malformed / empty / non-str
input degrades to `[]`, mirroring the never-raises resolvers in
`verification/reproduce.py` (see `tests/test_reproduce_locator.py`).
"""

from __future__ import annotations

import dataclasses
import math

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


# ---------------------------------------------------------------------------
# Phase 3: robustness + the labeled fixture corpus
# ---------------------------------------------------------------------------


def test_extract_claims_never_raises_on_wild_inputs():
    # Mirror of tests/test_reproduce_locator.py's never-raises test: a grab-bag
    # of adversarial inputs must always yield a list, never an exception.
    wild_inputs = [
        "",
        "   \n\t  ",
        "no numbers or metrics here at all",
        "\x00\x01\x02 control chars and \x7f delete",
        "AUC of",  # metric + connective, no number
        "0.9 0.9 0.9 AUC",  # numbers before the metric
        "%%% ::: === <<< >>>",
        "AUC of <=>= 0.5",
        "r² r-squared r2 correlation pearson spearman",
        "AUC of 1e999999 and accuracy of nan and recall of inf",
        # a wall of prose with 100 numbers and scattered metric words
        (" ".join(f"value {i} was {i}.{i}" for i in range(100))
         + " AUC of 0.9 accuracy of 88%"),
    ]
    for text in wild_inputs:
        result = extract_claims(text)
        assert isinstance(result, list)
        for claim in result:
            assert isinstance(claim, ExtractedClaim)

    # non-str inputs degrade to [] rather than raising
    for bad in [None, 123, 3.14, ["AUC of 0.9"], {"text": "AUC of 0.9"}, b"AUC of 0.9"]:
        assert extract_claims(bad) == []  # type: ignore[arg-type]


# Labeled fixture corpus: short paper-excerpt strings, each paired with the
# hand-labeled set of (metric_slug, value, unit) it should yield. The bar is
# "recovers every labeled claim, emits zero malformed entries" (PRD goal #3).
_CORPUS: tuple[tuple[str, str, set[tuple[str, float, str | None]]], ...] = (
    (
        "ml_results",
        "On the held-out test set the classifier achieved an AUC of 0.94 and "
        "an accuracy of 91%. The F1 score was 0.88, while precision reached "
        "0.90 and recall was 0.86.",
        {
            ("auc", 0.94, None),
            ("accuracy", 91.0, "%"),
            ("f1_score", 0.88, None),
            ("precision", 0.90, None),
            ("recall", 0.86, None),
        },
    ),
    (
        "genomics_de",
        "Differential expression analysis identified a log2 fold change of "
        "-2.3 for the gene, with a Pearson correlation of 0.76 between "
        "replicates. Specificity was 0.98.",
        {
            ("log2_fold_change", -2.3, None),
            ("correlation", 0.76, None),
            ("specificity", 0.98, None),
        },
    ),
    (
        "percent_and_inequality",
        "The assay reached a sensitivity of 95% and a specificity of 88%. All "
        "p-values were < 0.001, and the RMSE was 0.12.",
        {
            ("sensitivity", 95.0, "%"),
            ("specificity", 88.0, "%"),
            ("rmse", 0.12, None),
        },
    ),
    (
        "duplicate_and_distinct",
        "In the abstract we state an AUC of 0.90. As shown in Table 2, the AUC "
        "of 0.90 is confirmed, and the MAE was 0.05.",
        {
            ("auc", 0.90, None),
            ("mae", 0.05, None),
        },
    ),
)


def test_corpus_recovers_every_labeled_claim_with_no_malformed_entries():
    for name, text, expected in _CORPUS:
        claims = extract_claims(text)
        got = {(_slug(c.metric), c.value, c.unit) for c in claims}
        # recall: every labeled claim is recovered
        assert expected <= got, f"{name}: missed {expected - got}"
        # precision on the corpus: no spurious extra claims
        assert got == expected, f"{name}: unexpected extras {got - expected}"
        # zero malformed: finite float value, non-empty id, unit is None or "%"
        for c in claims:
            assert isinstance(c.value, float) and math.isfinite(c.value)
            assert isinstance(c.id, str) and c.id
            assert c.unit in (None, "%")


def test_corpus_percentage_keeps_raw_value_not_divided():
    (_, text, _) = _CORPUS[2]  # percent_and_inequality
    by_slug = {_slug(c.metric): c for c in extract_claims(text)}
    assert by_slug["sensitivity"].value == 95.0
    assert by_slug["sensitivity"].unit == "%"


def test_corpus_inequality_value_is_absent():
    (_, text, _) = _CORPUS[2]
    assert all(c.value != 0.001 for c in extract_claims(text))


def test_corpus_duplicate_collapses_to_one_claim():
    (_, text, _) = _CORPUS[3]  # duplicate_and_distinct
    claims = extract_claims(text)
    auc_claims = [c for c in claims if _slug(c.metric) == "auc"]
    assert len(auc_claims) == 1
    assert "abstract" in auc_claims[0].source_text
