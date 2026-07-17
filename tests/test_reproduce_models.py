import pytest
from pydantic import ValidationError

from contig.models import ClaimResult, ReproduceRecord
from contig.verification.reproduce import reduce_reproduction


def _claim(id_="c1", status="reproduced", claimed=0.9, observed=0.9, tolerance=0.02, delta=0.0):
    return ClaimResult(
        id=id_,
        status=status,
        claimed=claimed,
        observed=observed,
        tolerance=tolerance,
        delta=delta,
        message="ok",
    )


def test_claim_result_round_trips_via_json():
    claim = _claim()
    restored = ClaimResult.model_validate_json(claim.model_dump_json())
    assert restored == claim


def test_claim_result_allows_none_observed_and_delta_when_uncomputable():
    claim = ClaimResult(
        id="c2",
        status="unverified",
        claimed=0.9,
        observed=None,
        tolerance=0.02,
        delta=None,
        message="metric not found in output",
    )
    restored = ClaimResult.model_validate_json(claim.model_dump_json())
    assert restored.observed is None
    assert restored.delta is None


def test_claim_result_rejects_unknown_status():
    with pytest.raises(ValidationError):
        ClaimResult(
            id="c1",
            status="approximately_true",
            claimed=0.9,
            observed=0.9,
            tolerance=0.02,
            delta=0.0,
            message="x",
        )


def test_reproduce_record_round_trips_via_json():
    record = ReproduceRecord(
        reproduce_id="rp_1",
        repo="https://github.com/example/paper",
        run_command="contig reproduce https://github.com/example/paper",
        claims_sha256="a" * 64,
        claim_results=[_claim()],
        exit_code=0,
        created_at="2026-07-18T00:00:00Z",
        interpreter="cpython-3.12",
        tool="contig",
    )
    restored = ReproduceRecord.model_validate_json(record.model_dump_json())
    assert restored == record


def test_reproduce_record_minimal_without_defaulted_fields_validates():
    # Old/minimal records (no interpreter, no tool) must still validate.
    record = ReproduceRecord.model_validate(
        {
            "reproduce_id": "rp_2",
            "repo": "https://github.com/example/paper",
            "run_command": "contig reproduce https://github.com/example/paper",
            "claims_sha256": "b" * 64,
            "claim_results": [],
            "exit_code": 1,
            "created_at": "2026-07-18T00:00:00Z",
        }
    )
    assert record.interpreter is None
    assert record.tool == "contig"


def test_reduce_reproduction_mixed_counts_and_summary():
    results = [
        _claim(id_="a", status="reproduced"),
        _claim(id_="b", status="reproduced"),
        _claim(id_="c", status="within_tolerance"),
        _claim(id_="d", status="diverged"),
    ]
    reduced = reduce_reproduction(results)
    assert reduced["reproduced"] == 2
    assert reduced["within_tolerance"] == 1
    assert reduced["diverged"] == 1
    assert reduced["unverified"] == 0
    assert "2" in reduced["summary"] or "reproduced" in reduced["summary"]


def test_reduce_reproduction_all_reproduced():
    results = [_claim(id_="a"), _claim(id_="b")]
    reduced = reduce_reproduction(results)
    assert reduced["reproduced"] == 2
    assert reduced["diverged"] == 0
    assert reduced["unverified"] == 0
    assert reduced["within_tolerance"] == 0
    assert "2/2 reproduced" in reduced["summary"]


def test_reduce_reproduction_never_upgrades_diverged_or_unverified():
    results = [
        _claim(id_="a", status="diverged"),
        _claim(id_="b", status="unverified"),
    ]
    reduced = reduce_reproduction(results)
    assert reduced["reproduced"] == 0
    assert reduced["diverged"] == 1
    assert reduced["unverified"] == 1


def test_reduce_reproduction_empty_list_reports_no_claims_without_crashing():
    reduced = reduce_reproduction([])
    assert reduced["reproduced"] == 0
    assert reduced["within_tolerance"] == 0
    assert reduced["diverged"] == 0
    assert reduced["unverified"] == 0
    assert "no claims" in reduced["summary"].lower()
