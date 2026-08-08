"""Tests for the verification-corpus models (C6 fold-in, aspect 1).

The labeling design (PRD R1): a `VerificationCase` carries pre-band signal
values plus a human-confirmed verdict label, and the eval/snapshot/guard
models mirror `EvalSnapshot`/`HoldoutGuardResult`/`HealSnapshot`/
`HealGuardResult` (which is why the guard machinery can reuse the same
history/baseline plumbing). All new fields are additive with defaults so a
bundle serialized before the fold-in loads unchanged.
"""

from __future__ import annotations

from contig.models import (
    FamilyScore,
    VerificationCase,
    VerifyCaseResult,
    VerifyEvalReport,
    VerifyGuardResult,
    VerifySnapshot,
)


def _case() -> VerificationCase:
    return VerificationCase(
        case_id="verify-1",
        description="pins the germline ts_tv warn band",
        source="synthetic",
        assay="variant_calling",
        inputs={"germline": {"S1": {"ts_tv": 1.5}}},
        expected_verdict="warn",
    )


# --- VerificationCase --------------------------------------------------------


def test_verification_case_defaults():
    case = _case()
    assert case.expected_verdict == "warn"
    unlabeled = VerificationCase(
        case_id="verify-2",
        description="d",
        source="synthetic",
        assay="rnaseq",
        inputs={},
    )
    assert unlabeled.expected_verdict is None
    assert unlabeled.known_miss is False


def test_verification_case_json_round_trip():
    case = _case()
    assert VerificationCase.model_validate_json(case.model_dump_json()) == case


def test_verification_case_known_miss_flag():
    case = _case().model_copy(update={"known_miss": True})
    assert case.known_miss is True
    assert VerificationCase.model_validate_json(case.model_dump_json()) == case


def test_pre_existing_bundle_without_new_fields_loads():
    # Back-compat: a case written before `known_miss` existed (and before a
    # verdict was assigned) must deserialize unchanged, with both fields at
    # their defaults.
    old = (
        '{"case_id": "verify-0", "description": "d", "source": "synthetic", '
        '"assay": "germline", "inputs": {}}'
    )
    case = VerificationCase.model_validate_json(old)
    assert case.expected_verdict is None
    assert case.known_miss is False


def test_expected_verdict_rejects_unknown_status():
    import pytest

    with pytest.raises(ValueError):
        VerificationCase(
            case_id="verify-3",
            description="d",
            source="synthetic",
            assay="rnaseq",
            inputs={},
            expected_verdict="maybe",  # type: ignore[arg-type]
        )


# --- FamilyScore / VerifyCaseResult ------------------------------------------


def test_family_score_defaults():
    score = FamilyScore(matched=2, total=3, rate=2 / 3)
    assert score.rate == 2 / 3


def test_verify_case_result_defaults():
    result = VerifyCaseResult(
        case_id="verify-1",
        predicted_verdict="warn",
        expected_verdict="warn",
        matched=True,
        families={"germline": "warn"},
    )
    assert result.divergence == []
    assert VerifyCaseResult.model_validate_json(result.model_dump_json()) == result


# --- VerifyEvalReport / VerifySnapshot / VerifyGuardResult -------------------


def test_verify_eval_report_defaults():
    report = VerifyEvalReport(total=10, correct=8, verdict_match_rate=0.8)
    assert report.per_family == {}
    assert report.mismatches == []
    assert VerifyEvalReport.model_validate_json(report.model_dump_json()) == report


def test_verify_snapshot_defaults():
    snapshot = VerifySnapshot(
        timestamp="2026-08-09T00:00:00+00:00",
        case_count=10,
        corpus_sha="sha",
        verdict_match_rate=0.8,
    )
    assert snapshot.per_family == {}
    assert snapshot.contig_version is None
    assert VerifySnapshot.model_validate_json(snapshot.model_dump_json()) == snapshot


def test_verify_guard_result_defaults():
    result = VerifyGuardResult(
        case_count=10,
        verdict_match_rate=0.8,
        tolerance=1e-9,
        corpus_sha="sha",
    )
    assert result.baseline_rate is None
    assert result.delta is None
    assert result.regressed is False
    assert result.improved is False
    assert result.baseline_sha is None
    assert result.sha_mismatch is False
    assert result.has_baseline is True
    assert result.mismatches == []
    assert VerifyGuardResult.model_validate_json(result.model_dump_json()) == result


def test_verify_guard_result_carries_mismatches():
    mismatch = VerifyCaseResult(
        case_id="verify-1",
        predicted_verdict="fail",
        expected_verdict="warn",
        matched=False,
        families={"germline": "fail"},
        divergence=["expected warn but predicted fail"],
    )
    result = VerifyGuardResult(
        case_count=1,
        verdict_match_rate=0.0,
        tolerance=1e-9,
        corpus_sha="sha",
        mismatches=[mismatch],
    )
    assert result.mismatches[0].case_id == "verify-1"
    assert VerifyGuardResult.model_validate_json(result.model_dump_json()) == result
