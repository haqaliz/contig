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
    _slug,
    extract_claims,
)


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
