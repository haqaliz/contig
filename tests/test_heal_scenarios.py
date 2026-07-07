"""Tests for the heal-guard models (C6 slice 2: self-heal outcome-match guard).

Task 1 only: the 7 new Pydantic models exist, carry the documented defaults,
and round-trip through JSON. No CLI/logic here -- that's later tasks.
"""

from __future__ import annotations

import pytest

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


# --- run_heal_scenario / evaluate_heal (Task 2: real self-heal driver) -----

from contig.heal import evaluate_heal, run_heal_scenario  # noqa: E402


def test_run_heal_scenario_oom_recovers(tmp_path):
    # Transcribed from test_self_heal.py:49-66 (test_self_heal_recovers_from_oom_and_logs_repair).
    scn = HealScenario(
        scenario_id="oom-1",
        description="OOM on star_align, retried with bumped memory",
        source="synthetic",
        expected_class="oom",
        attempts=[
            AttemptSpec(status="FAILED", exit=137, log_text="Process killed: out of memory (exit 137)"),
            AttemptSpec(status="COMPLETED", exit=0, log_text="done"),
        ],
        expected_recovered=True,
        expected_outcome="patched_and_retried",
    )
    result = run_heal_scenario(scn, tmp_path)
    assert result.matched is True
    assert result.diagnosed_class == "oom"
    assert result.recovered is True
    assert result.actual_outcome == "patched_and_retried"
    assert result.divergence == []


def test_run_heal_scenario_tool_crash_gives_up(tmp_path):
    # Transcribed from test_self_heal.py:140-148 (test_self_heal_gives_up_on_unrecoverable_tool_crash).
    scn = HealScenario(
        scenario_id="tool-crash-1",
        description="Segfault in some_tool is unrecoverable",
        source="synthetic",
        expected_class="tool_crash",
        attempts=[
            AttemptSpec(status="FAILED", exit=1, log_text="Segmentation fault in some_tool"),
        ],
        expected_recovered=False,
        expected_outcome="gave_up",
    )
    result = run_heal_scenario(scn, tmp_path)
    assert result.matched is True
    assert result.diagnosed_class == "tool_crash"
    assert result.recovered is False
    assert result.actual_outcome == "gave_up"


def test_run_heal_scenario_bwa_missing_index_unresolvable(tmp_path):
    # Transcribed from test_self_heal.py:190-216
    # (test_self_heal_bwa_missing_index_gives_up_unresolvable). The bwa signature
    # is detected as missing_index but its evidence line carries no parseable
    # index path, so the loop must give up honestly with index_unresolvable.
    scn = HealScenario(
        scenario_id="bwa-missing-index-1",
        description="bwa missing-index signature is unresolvable (no parseable path)",
        source="synthetic",
        expected_class="missing_index",
        attempts=[
            AttemptSpec(
                status="FAILED",
                exit=1,
                log_text="[E::bwa_idx_load_from_disk] fail to locate the index files",
            ),
        ],
        auto_approve=True,
        index_builder_result="success",
        expected_recovered=False,
        expected_outcome="index_unresolvable",
    )
    result = run_heal_scenario(scn, tmp_path)
    assert result.matched is True
    assert result.diagnosed_class == "missing_index"
    assert result.recovered is False
    assert result.actual_outcome == "index_unresolvable"


def test_evaluate_heal_aggregates_rates(tmp_path):
    oom_scn = HealScenario(
        scenario_id="oom-1",
        description="OOM recovers",
        source="synthetic",
        expected_class="oom",
        attempts=[
            AttemptSpec(status="FAILED", exit=137, log_text="Process killed: out of memory (exit 137)"),
            AttemptSpec(status="COMPLETED", exit=0, log_text="done"),
        ],
        expected_recovered=True,
        expected_outcome="patched_and_retried",
    )
    tool_crash_scn = HealScenario(
        scenario_id="tool-crash-1",
        description="Segfault is unrecoverable",
        source="synthetic",
        expected_class="tool_crash",
        attempts=[
            AttemptSpec(status="FAILED", exit=1, log_text="Segmentation fault in some_tool"),
        ],
        expected_recovered=False,
        expected_outcome="gave_up",
    )
    # A scenario that will NOT match (expects the wrong outcome) so mismatches
    # and the aggregate rate below 1.0 are both exercised.
    mismatched_scn = HealScenario(
        scenario_id="tool-crash-mismatch",
        description="Segfault, but we (incorrectly) expect it to recover",
        source="synthetic",
        expected_class="tool_crash",
        attempts=[
            AttemptSpec(status="FAILED", exit=1, log_text="Segmentation fault in some_tool"),
        ],
        expected_recovered=True,
        expected_outcome="patched_and_retried",
    )

    report = evaluate_heal([oom_scn, tool_crash_scn, mismatched_scn])

    assert report.total == 3
    assert report.matched == 2
    assert report.outcome_match_rate == pytest.approx(2 / 3)
    assert report.healed == 1
    assert report.recovery_rate == pytest.approx(1 / 3)
    assert set(report.per_class) == {"oom", "tool_crash"}
    assert report.per_class["tool_crash"].total == 2
    assert report.per_class["tool_crash"].matched == 1
    assert len(report.mismatches) == 1
    assert report.mismatches[0].scenario_id == "tool-crash-mismatch"
