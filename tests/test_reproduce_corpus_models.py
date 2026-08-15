"""Tests for the reproduce-case corpus models (C8 slice: pure data models).

A `ReproduceCase` is one labeled case in the reproduce corpus: a published
repo + run command + claims, re-derived through the REAL reproduce loop to
produce a `ReproduceCaseResult`, aggregated into a `ReproduceCorpusReport`
and committed as a `ReproduceCorpusSnapshot`. These tests pin the model
contracts -- defaults, required fields, literal validation, JSON round-trip --
mirroring the verify-corpus/reproduce-guard model tests.
"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from contig.models import (
    FamilyScore,
    ReproduceCase,
    ReproduceCaseClaim,
    ReproduceCaseResult,
    ReproduceCorpusReport,
    ReproduceCorpusSnapshot,
)


# --- Defaults -----------------------------------------------------------------


def test_reproduce_case_claim_defaults():
    claim = ReproduceCaseClaim(
        claim_id="c1", claimed=0.91, tolerance=1e-9, family="flat"
    )
    dumped = claim.model_dump()
    assert dumped["observed"] is None
    assert dumped["expected_status"] is None


def test_reproduce_case_defaults():
    case = ReproduceCase(
        case_id="paper-2024-001",
        description="d",
        source="synthetic",
        repo="https://example.org/repo.git",
        run_command="python script.py",
        claims_sha256="a" * 64,
        exit_code=0,
    )
    assert case.claims == []
    assert case.repair is None
    assert case.expected_exit_code is None
    assert case.known_miss is False


# --- Full case round-trip -----------------------------------------------------


def _full_case() -> ReproduceCase:
    return ReproduceCase(
        case_id="paper-2024-001",
        description="RNA-seq pipeline F1 claim",
        source="synthetic",
        repo="https://example.org/repo.git",
        run_command="python script.py",
        claims_sha256="b" * 64,
        claims=[
            ReproduceCaseClaim(
                claim_id="f1",
                claimed=0.91,
                observed=0.91,
                tolerance=1e-9,
                family="flat",
                expected_status="reproduced",
            ),
            ReproduceCaseClaim(
                claim_id="f2",
                claimed=0.85,
                observed=0.82,
                tolerance=0.05,
                family="notebook",
                expected_status="diverged",
            ),
        ],
        repair="installed_and_retried",
        exit_code=0,
        expected_exit_code=0,
        known_miss=True,
    )


def test_full_reproduce_case_round_trips_byte_identically():
    case = _full_case()
    serialized = case.model_dump_json()
    parsed = ReproduceCase.model_validate_json(serialized)
    assert parsed == case
    assert parsed.model_dump_json() == serialized


def test_reproduce_case_claim_round_trips_json():
    claim = _full_case().claims[0]
    parsed = ReproduceCaseClaim.model_validate_json(claim.model_dump_json())
    assert parsed == claim
    assert parsed.model_dump_json() == claim.model_dump_json()


# --- Validation ---------------------------------------------------------------


def test_reproduce_case_claim_rejects_bogus_expected_status():
    with pytest.raises(ValidationError):
        ReproduceCaseClaim(
            claim_id="c1",
            claimed=0.91,
            tolerance=1e-9,
            family="flat",
            expected_status="bogus",
        )


def test_reproduce_case_rejects_bogus_repair():
    with pytest.raises(ValidationError):
        ReproduceCase(
            case_id="c",
            description="d",
            source="synthetic",
            repo="r",
            run_command="cmd",
            claims_sha256="a" * 64,
            exit_code=0,
            repair="bogus",
        )


def test_reproduce_case_requires_exit_code():
    with pytest.raises(ValidationError):
        ReproduceCase(
            case_id="c",
            description="d",
            source="synthetic",
            repo="r",
            run_command="cmd",
            claims_sha256="a" * 64,
        )


def test_reproduce_case_result_predicted_statuses_are_plain_strings():
    result = ReproduceCaseResult(
        case_id="c",
        predicted_statuses={"f1": "reproduced"},
        matched=True,
        labeled_claims=1,
        matching_claims=1,
    )
    assert result.predicted_statuses == {"f1": "reproduced"}


# --- Report / Snapshot --------------------------------------------------------


def test_reproduce_corpus_report_with_family_scores_and_mismatches():
    report = ReproduceCorpusReport(
        total=2,
        correct=1,
        claim_match_rate=0.5,
        cases=1,
        per_family={
            "flat": FamilyScore(matched=1, total=1, rate=1.0),
            "notebook": FamilyScore(matched=0, total=1, rate=0.0),
        },
        mismatches=[
            ReproduceCaseResult(
                case_id="paper-2024-001",
                predicted_statuses={"f2": "diverged"},
                matched=False,
                labeled_claims=2,
                matching_claims=1,
                divergence=["f2"],
            )
        ],
    )
    assert report.total == 2
    assert report.correct == 1
    assert report.claim_match_rate == 0.5
    assert report.cases == 1
    assert report.per_family["flat"].rate == 1.0
    assert report.per_family["notebook"].rate == 0.0
    assert report.mismatches[0].case_id == "paper-2024-001"
    assert report.mismatches[0].divergence == ["f2"]
    assert report.mismatches[0].predicted_statuses == {"f2": "diverged"}
    assert report.mismatches[0].labeled_claims == 2
    assert report.mismatches[0].matching_claims == 1
    parsed = ReproduceCorpusReport.model_validate_json(report.model_dump_json())
    assert parsed == report


def test_reproduce_case_result_defaults():
    result = ReproduceCaseResult(
        case_id="c",
        predicted_statuses={},
        matched=True,
        labeled_claims=0,
        matching_claims=0,
    )
    assert result.divergence == []


def test_reproduce_corpus_snapshot_with_family_scores_serializes():
    snapshot = ReproduceCorpusSnapshot(
        timestamp="2026-08-15T00:00:00Z",
        case_count=7,
        corpus_sha="c" * 64,
        claim_match_rate=6 / 7,
        per_family={
            "flat": FamilyScore(matched=3, total=3, rate=1.0),
            "notebook": FamilyScore(matched=3, total=4, rate=0.75),
        },
        contig_version="0.54.0",
    )
    assert snapshot.timestamp == "2026-08-15T00:00:00Z"
    assert snapshot.case_count == 7
    assert snapshot.corpus_sha == "c" * 64
    assert snapshot.claim_match_rate == 6 / 7
    assert snapshot.per_family["notebook"].rate == 0.75
    assert snapshot.contig_version == "0.54.0"
    parsed = ReproduceCorpusSnapshot.model_validate_json(snapshot.model_dump_json())
    assert parsed == snapshot
    assert parsed.model_dump_json() == snapshot.model_dump_json()


def test_reproduce_corpus_snapshot_defaults():
    snapshot = ReproduceCorpusSnapshot(
        timestamp="t",
        case_count=0,
        corpus_sha="d" * 64,
        claim_match_rate=0.0,
    )
    assert snapshot.per_family == {}
    assert snapshot.contig_version is None


def test_reproduce_corpus_report_jsonl_shape():
    report = ReproduceCorpusReport(
        total=1,
        correct=1,
        claim_match_rate=1.0,
        cases=1,
    )
    assert json.loads(report.model_dump_json()) == {
        "total": 1,
        "correct": 1,
        "claim_match_rate": 1.0,
        "cases": 1,
        "per_family": {},
        "mismatches": [],
    }
