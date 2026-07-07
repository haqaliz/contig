"""Tests for the heal-guard models (C6 slice 2: self-heal outcome-match guard).

Task 1 only: the 7 new Pydantic models exist, carry the documented defaults,
and round-trip through JSON. No CLI/logic here -- that's later tasks.
"""

from __future__ import annotations

from contig.models import (
    AttemptSpec,
    HealClassScore,
    HealEvalReport,
    HealGuardResult,
    HealScenario,
    HealScenarioResult,
    HealSnapshot,
)

# --- HealScenario + AttemptSpec --------------------------------------------


def test_heal_scenario_constructs_from_dict_with_defaults():
    scenario = HealScenario.model_validate(
        {
            "scenario_id": "heal-001",
            "description": "OOM on star_align, retried with bumped memory",
            "source": "synthetic",
            "expected_class": "oom",
            "attempts": [
                {"status": "failed", "exit": 137, "log_text": "Out of memory"},
            ],
            "expected_recovered": True,
            "expected_outcome": "pass",
        }
    )
    assert isinstance(scenario.attempts[0], AttemptSpec)
    assert scenario.attempts[0].status == "failed"
    assert scenario.attempts[0].exit == 137
    assert scenario.attempts[0].log_text == "Out of memory"
    # Documented defaults.
    assert scenario.auto_approve is False
    assert scenario.poll_decision is None
    assert scenario.resource_ceiling is None
    assert scenario.index_builder_result is None
    assert scenario.max_attempts == 3
    assert scenario.assay == "rnaseq"


def test_heal_scenario_json_round_trip():
    scenario = HealScenario(
        scenario_id="heal-002",
        description="missing index triggers index_builder",
        source="run:abc123",
        expected_class="missing_index",
        attempts=[AttemptSpec(status="failed", exit=1)],
        expected_recovered=True,
        expected_outcome="pass",
    )
    round_tripped = HealScenario.model_validate_json(scenario.model_dump_json())
    assert round_tripped == scenario
    assert round_tripped.attempts[0].log_text == ""


# --- HealClassScore / HealScenarioResult / HealEvalReport ------------------


def test_heal_class_score_constructs():
    score = HealClassScore(matched=3, total=4, rate=0.75)
    assert score.matched == 3
    assert score.total == 4
    assert score.rate == 0.75


def test_heal_scenario_result_constructs():
    result = HealScenarioResult(
        scenario_id="heal-001",
        diagnosed_class="oom",
        recovered=True,
        actual_outcome="pass",
        matched=True,
        divergence=[],
    )
    assert result.matched is True
    assert result.divergence == []


def test_heal_eval_report_constructs():
    report = HealEvalReport(
        total=10,
        matched=8,
        outcome_match_rate=0.8,
        healed=7,
        recovery_rate=0.7,
        per_class={"oom": HealClassScore(matched=3, total=4, rate=0.75)},
        mismatches=[],
    )
    assert report.total == 10
    assert report.per_class["oom"].total == 4


# --- HealSnapshot / HealGuardResult ----------------------------------------


def test_heal_snapshot_dump_json():
    snapshot = HealSnapshot(
        timestamp="2026-07-07T00:00:00Z",
        scenario_count=10,
        corpus_sha="deadbeef",
        outcome_match_rate=0.8,
        recovery_rate=0.7,
        per_class={"oom": HealClassScore(matched=3, total=4, rate=0.75)},
        covered_classes=["oom", "missing_index"],
    )
    payload = snapshot.model_dump_json()
    assert '"corpus_sha":"deadbeef"' in payload
    reloaded = HealSnapshot.model_validate_json(payload)
    assert reloaded == snapshot
    assert reloaded.contig_version is None


def test_heal_guard_result_dump_json():
    result = HealGuardResult(
        scenario_count=10,
        outcome_match_rate=0.8,
        baseline_match_rate=0.75,
        delta=0.05,
        tolerance=0.02,
        regressed=False,
        improved=True,
        recovery_rate=0.7,
        corpus_sha="deadbeef",
        baseline_sha="deadbeef",
        sha_mismatch=False,
        has_baseline=True,
        mismatches=[],
    )
    payload = result.model_dump_json()
    assert '"regressed":false' in payload
    reloaded = HealGuardResult.model_validate_json(payload)
    assert reloaded == result
