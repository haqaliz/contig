"""Tests for the reproduce-guard models and default data paths (C6 fold-in,
guard-core aspect, Phase A).

The guard replays frozen `ReproduceScenario`s through the REAL
`run_reproduction` loop; these tests pin the model contracts the replay is
built on -- defaults, required fields, snapshot round-trip -- plus the default
data-file paths, mirroring the verify-guard/heal-guard model tests.
"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from contig.models import (
    ExecStep,
    FamilyScore,
    ReproduceRecord,
    ReproduceScenario,
    ReproduceSnapshot,
)
from contig.reproduce_guard import (
    default_reproduce_baseline_path,
    default_reproduce_history_path,
    default_reproduce_scenarios_path,
)


def _full_scenario_dict() -> dict:
    return {
        "scenario_id": "flat-exact",
        "description": "flat results.json, exact value",
        "source": "holdout:synthetic",
        "run_command": "python script.py",
        "claims": [{"id": "c1", "value": 0.91}],
        "results_path": "results.json",
        "executor_steps": [
            {
                "exit_code": 0,
                "output": "done",
                "write_results": {"c1": 0.91},
                "write_artifacts": {"out/metric.txt": "0.91"},
                "artifact_mtimes": {"out/metric.txt": 1_000_000.0},
            }
        ],
        "installer_steps": [0],
        "allow_install": True,
        "expected_claim_statuses": {"c1": "reproduced"},
        "expected_repair": "installed_and_retried",
        "expected_exit_code": 0,
        "known_miss": True,
    }


# --- ReproduceScenario --------------------------------------------------------


def test_reproduce_scenario_parses_from_jsonl_line_with_all_fields():
    scenario = ReproduceScenario.model_validate_json(
        json.dumps(_full_scenario_dict())
    )
    assert scenario.scenario_id == "flat-exact"
    assert scenario.description == "flat results.json, exact value"
    assert scenario.source == "holdout:synthetic"
    assert scenario.run_command == "python script.py"
    assert scenario.claims == [{"id": "c1", "value": 0.91}]
    assert scenario.results_path == "results.json"
    assert len(scenario.executor_steps) == 1
    step = scenario.executor_steps[0]
    assert step.exit_code == 0
    assert step.output == "done"
    assert step.write_results == {"c1": 0.91}
    assert step.write_artifacts == {"out/metric.txt": "0.91"}
    assert step.artifact_mtimes == {"out/metric.txt": 1_000_000.0}
    assert scenario.installer_steps == [0]
    assert scenario.allow_install is True
    assert scenario.expected_claim_statuses == {"c1": "reproduced"}
    assert scenario.expected_repair == "installed_and_retried"
    assert scenario.expected_exit_code == 0
    assert scenario.known_miss is True


def test_reproduce_scenario_defaults_hold():
    scenario = ReproduceScenario(
        scenario_id="s1",
        description="d",
        run_command="cmd",
        claims=[],
        executor_steps=[ExecStep()],
        expected_claim_statuses={},
    )
    assert scenario.source == "holdout:synthetic"
    assert scenario.results_path == "results.json"
    assert scenario.installer_steps is None
    assert scenario.allow_install is False
    assert scenario.expected_repair == "none"
    assert scenario.expected_exit_code == 0
    assert scenario.known_miss is False


def test_reproduce_scenario_requires_executor_steps():
    with pytest.raises(ValidationError):
        ReproduceScenario(
            scenario_id="s1",
            description="d",
            run_command="cmd",
            claims=[],
            expected_claim_statuses={},
        )


def test_reproduce_scenario_requires_expected_claim_statuses():
    with pytest.raises(ValidationError):
        ReproduceScenario(
            scenario_id="s1",
            description="d",
            run_command="cmd",
            claims=[],
            executor_steps=[ExecStep()],
        )


def test_reproduce_scenario_expected_repair_is_a_literal():
    with pytest.raises(ValidationError):
        ReproduceScenario(
            scenario_id="s1",
            description="d",
            run_command="cmd",
            claims=[],
            executor_steps=[ExecStep()],
            expected_claim_statuses={},
            expected_repair="made_up",
        )


# --- ExecStep -----------------------------------------------------------------


def test_exec_step_parses_with_defaults():
    step = ExecStep()
    assert step.exit_code == 0
    assert step.output == ""
    assert step.write_results is None
    assert step.write_artifacts is None
    assert step.artifact_mtimes is None


def test_exec_step_artifact_dicts_are_dicts():
    step = ExecStep(
        exit_code=1,
        output="No module named 'x'",
        write_results={"c1": 0.5},
        write_artifacts={"out/a.txt": "a", "out/b.txt": "b"},
        artifact_mtimes={"out/a.txt": 1_000_000.0, "out/b.txt": 999_999.0},
    )
    assert step.write_artifacts == {"out/a.txt": "a", "out/b.txt": "b"}
    assert step.artifact_mtimes == {"out/a.txt": 1_000_000.0, "out/b.txt": 999_999.0}
    assert isinstance(step.write_artifacts, dict)
    assert isinstance(step.artifact_mtimes, dict)
    assert isinstance(step.artifact_mtimes["out/a.txt"], float)


# --- ReproduceSnapshot --------------------------------------------------------


def test_reproduce_snapshot_fields_exist():
    snapshot = ReproduceSnapshot(
        timestamp="2026-08-14T00:00:00Z",
        scenario_count=14,
        corpus_sha="a" * 64,
        outcome_match_rate=13 / 14,
        recovery_rate=1 / 14,
        per_family={
            "flat": FamilyScore(matched=1, total=1, rate=1.0),
            "notebook": FamilyScore(matched=1, total=1, rate=1.0),
        },
        covered_families=["flat", "notebook"],
        contig_version="0.54.0",
    )
    assert snapshot.timestamp == "2026-08-14T00:00:00Z"
    assert snapshot.scenario_count == 14
    assert snapshot.corpus_sha == "a" * 64
    assert snapshot.outcome_match_rate == 13 / 14
    assert snapshot.recovery_rate == 1 / 14
    assert isinstance(snapshot.per_family, dict)
    assert snapshot.per_family["flat"].rate == 1.0
    assert snapshot.covered_families == ["flat", "notebook"]
    assert snapshot.contig_version == "0.54.0"


def test_reproduce_snapshot_per_family_optional():
    snapshot = ReproduceSnapshot(
        timestamp="t",
        scenario_count=1,
        corpus_sha="a" * 64,
        outcome_match_rate=1.0,
        recovery_rate=0.0,
        covered_families=[],
        contig_version="0.54.0",
    )
    assert snapshot.per_family is None


def test_reproduce_snapshot_round_trip_json():
    snapshot = ReproduceSnapshot(
        timestamp="2026-08-14T00:00:00Z",
        scenario_count=14,
        corpus_sha="a" * 64,
        outcome_match_rate=13 / 14,
        recovery_rate=1 / 14,
        per_family={"flat": FamilyScore(matched=1, total=1, rate=1.0)},
        covered_families=["flat"],
        contig_version="0.54.0",
    )
    parsed = ReproduceSnapshot.model_validate_json(snapshot.model_dump_json())
    assert parsed == snapshot


# --- Back-compat: ReproduceRecord is untouched by this fold-in -----------------


def test_reproduce_record_back_compat_parses_stored_json_unchanged():
    stored = {
        "reproduce_id": "rp_1",
        "repo": "https://example.org/repo.git",
        "run_command": "python script.py",
        "claims_sha256": "a" * 64,
        "claim_results": [
            {
                "id": "c1",
                "status": "reproduced",
                "claimed": 0.91,
                "observed": 0.91,
                "tolerance": 1e-9,
                "delta": 0.0,
                "message": "exact match",
            }
        ],
        "exit_code": 0,
        "created_at": "2026-07-18T00:00:00Z",
    }
    record = ReproduceRecord.model_validate(stored)
    assert record.reproduce_id == "rp_1"
    assert record.exit_code == 0
    assert record.claim_results[0].status == "reproduced"
    assert record.repair_history == []


# --- default data paths -------------------------------------------------------


def test_default_reproduce_paths_resolve_under_data_dir():
    scenarios = default_reproduce_scenarios_path()
    baseline = default_reproduce_baseline_path()
    history = default_reproduce_history_path()
    assert scenarios.parent.name == "data"
    assert scenarios.parent == baseline.parent == history.parent
    assert scenarios.name == "reproduce_scenarios.jsonl"
    assert baseline.name == "reproduce_baseline.json"
    assert history.name == "reproduce_history.jsonl"
