"""Tests for the reproduce-guard scorer, snapshot, comparator, baseline I/O
(C6 fold-in, guard-core aspect, Phase C).

`evaluate_reproduce` replays every scenario through the REAL
`run_reproduction` loop (via the Phase B driver) and scores each against its
expected claim statuses / repair / exit code. The load-bearing test is the
anti-tautology mutation control: flipping either an expected status or an
OBSERVED input (the replayed artifact value) flips the scenario's match --
proving the scorer re-derives from each replay and never compares stored
statuses.
"""

from __future__ import annotations

import json
from datetime import datetime

import pytest

from contig.models import (
    ExecStep,
    FamilyScore,
    ReproduceScenario,
    ReproduceSnapshot,
)
from contig.reproduce_guard import (
    compare_reproduce_to_baseline,
    evaluate_reproduce,
    load_reproduce_baseline,
    load_reproduce_scenarios,
    save_reproduce_baseline,
    snapshot_from_reproduce_report,
)

# Repo-wide deterministic identity convention (mirrors the driver tests).
_RUN_START = 1_000_000.0


def _scenario(**overrides) -> ReproduceScenario:
    base = dict(
        scenario_id="s1",
        description="fixture",
        run_command="python run.py",
        claims=[{"id": "auc", "value": 0.9}],
        executor_steps=[ExecStep(exit_code=0, output="", write_results={"auc": 0.9})],
        expected_claim_statuses={"auc": "reproduced"},
        expected_repair="none",
        expected_exit_code=0,
    )
    base.update(overrides)
    return ReproduceScenario(**base)


def _heal_scenario(**overrides) -> ReproduceScenario:
    base = dict(
        scenario_id="heal",
        description="env-resurrection heal",
        run_command="python run.py",
        claims=[{"id": "auc", "value": 0.9}],
        allow_install=True,
        installer_steps=[0],
        executor_steps=[
            ExecStep(exit_code=1, output="ModuleNotFoundError: No module named 'x'"),
            ExecStep(exit_code=0, output="", write_results={"auc": 0.9}),
        ],
        expected_claim_statuses={"auc": "reproduced"},
        expected_repair="installed_and_retried",
        expected_exit_code=0,
    )
    base.update(overrides)
    return ReproduceScenario(**base)


def _snapshot(
    rate: float,
    *,
    corpus_sha: str = "sha-a",
    version: str = "0.53.0",
    covered: list[str] | None = None,
) -> ReproduceSnapshot:
    return ReproduceSnapshot(
        timestamp="2026-08-14T00:00:00+00:00",
        scenario_count=10,
        corpus_sha=corpus_sha,
        outcome_match_rate=rate,
        recovery_rate=0.0,
        per_family=None,
        covered_families=covered or ["flat"],
        contig_version=version,
    )


def _only_result(report: dict) -> dict:
    """The single per-scenario result dict out of a one-scenario report."""
    assert len(report["scenario_results"]) == 1
    return report["scenario_results"][0]


# --- 1. exact match semantics -------------------------------------------------


def test_scenario_matches_only_when_every_expectation_holds():
    report = evaluate_reproduce([_scenario()], run_started_at=_RUN_START)
    result = _only_result(report)
    assert result["scenario_id"] == "s1"
    assert result["matched"] is True
    assert result["mismatches"] == {}


def test_one_wrong_expected_claim_status_breaks_the_match():
    flipped = _scenario(expected_claim_statuses={"auc": "diverged"})
    result = _only_result(evaluate_reproduce([flipped], run_started_at=_RUN_START))
    assert result["matched"] is False
    assert result["mismatches"]["claim:auc"] == ("diverged", "reproduced")


def test_expected_repair_mismatch_breaks_the_match_independently():
    wrong_repair = _scenario(expected_repair="installed_and_retried")
    result = _only_result(
        evaluate_reproduce([wrong_repair], run_started_at=_RUN_START)
    )
    assert result["matched"] is False
    assert result["mismatches"]["repair"] == ("installed_and_retried", "none")


def test_expected_exit_code_mismatch_breaks_the_match_independently():
    wrong_exit = _scenario(expected_exit_code=5)
    result = _only_result(evaluate_reproduce([wrong_exit], run_started_at=_RUN_START))
    assert result["matched"] is False
    assert result["mismatches"]["exit_code"] == (5, 0)


def test_expected_claim_with_no_observed_result_never_matches():
    # The scenario's claims file has only "auc", but the expectation names a
    # claim id the replay never produced a result for: missing observed must
    # be a mismatch, never a pass.
    phantom = _scenario(expected_claim_statuses={"auc": "reproduced", "ghost": "reproduced"})
    result = _only_result(evaluate_reproduce([phantom], run_started_at=_RUN_START))
    assert result["matched"] is False
    assert result["mismatches"]["claim:ghost"] == ("reproduced", None)


# --- 2. UNVERIFIED never equals REPRODUCED ------------------------------------


def test_unverified_observed_never_matches_reproduced_expected():
    stale = _scenario(
        executor_steps=[
            ExecStep(
                exit_code=0,
                output="",
                write_results={"auc": 0.9},
                artifact_mtimes={"results.json": _RUN_START - 1},
            )
        ],
    )
    result = _only_result(evaluate_reproduce([stale], run_started_at=_RUN_START))
    assert result["matched"] is False
    assert result["mismatches"]["claim:auc"] == ("reproduced", "unverified")


def test_reproduced_observed_never_matches_unverified_expected():
    expecting_unverified = _scenario(expected_claim_statuses={"auc": "unverified"})
    result = _only_result(
        evaluate_reproduce([expecting_unverified], run_started_at=_RUN_START)
    )
    assert result["matched"] is False
    assert result["mismatches"]["claim:auc"] == ("unverified", "reproduced")


# --- 3. known_miss is metadata only -------------------------------------------


def test_known_miss_with_wrong_expected_status_scores_as_mismatch():
    known_miss = _scenario(
        scenario_id="km", known_miss=True, expected_claim_statuses={"auc": "diverged"}
    )
    report = evaluate_reproduce([known_miss], run_started_at=_RUN_START)
    result = _only_result(report)
    assert result["matched"] is False
    assert report["matched_count"] == 0
    assert report["total_count"] == 1


def test_known_miss_with_correct_expected_status_matches():
    known_miss = _scenario(scenario_id="km", known_miss=True)
    result = _only_result(
        evaluate_reproduce([known_miss], run_started_at=_RUN_START)
    )
    assert result["matched"] is True


# --- 4. anti-tautology mutation control (the load-bearing pin) ----------------


def test_mutation_control_expected_flip_flips_the_match():
    frozen = _scenario(scenario_id="mt")
    assert _only_result(
        evaluate_reproduce([frozen], run_started_at=_RUN_START)
    )["matched"] is True

    mutated_expected = frozen.model_copy(
        update={"expected_claim_statuses": {"auc": "diverged"}}
    )
    assert _only_result(
        evaluate_reproduce([mutated_expected], run_started_at=_RUN_START)
    )["matched"] is False


def test_mutation_control_observed_flip_flips_the_match():
    frozen = _scenario(scenario_id="mt")
    assert _only_result(
        evaluate_reproduce([frozen], run_started_at=_RUN_START)
    )["matched"] is True

    mutated_observed = _scenario(
        scenario_id="mt",
        executor_steps=[ExecStep(exit_code=0, output="", write_results={"auc": 0.5})],
    )
    flipped = _only_result(
        evaluate_reproduce([mutated_observed], run_started_at=_RUN_START)
    )
    assert flipped["matched"] is False
    assert flipped["mismatches"]["claim:auc"] == ("reproduced", "diverged")


# --- 5. outcome-match and recovery rates --------------------------------------


def test_rates_count_matched_and_healed_scenarios():
    scenarios = [
        _heal_scenario(),
        _scenario(
            scenario_id="install-fail",
            allow_install=True,
            installer_steps=[1],
            executor_steps=[ExecStep(exit_code=1, output="No module named 'x'")],
            expected_claim_statuses={"auc": "unverified"},
            expected_repair="install_failed",
            expected_exit_code=1,
        ),
        _scenario(scenario_id="bad", expected_claim_statuses={"auc": "diverged"}),
    ]
    report = evaluate_reproduce(scenarios, run_started_at=_RUN_START)

    assert report["matched_count"] == 2
    assert report["total_count"] == 3
    assert report["outcome_match_rate"] == pytest.approx(2 / 3)
    assert report["healed_count"] == 1
    assert report["recovery_rate"] == pytest.approx(1 / 3)
    matched_ids = [r["scenario_id"] for r in report["scenario_results"] if r["matched"]]
    assert matched_ids == ["heal", "install-fail"]


def test_recovery_rate_counts_only_installed_and_retried():
    # install_failed carries a repair_history entry but is NOT a recovery.
    report = evaluate_reproduce(
        [
            _scenario(
                scenario_id="install-fail",
                allow_install=True,
                installer_steps=[1],
                executor_steps=[ExecStep(exit_code=1, output="No module named 'x'")],
                expected_claim_statuses={"auc": "unverified"},
                expected_repair="install_failed",
                expected_exit_code=1,
            )
        ],
        run_started_at=_RUN_START,
    )
    assert report["healed_count"] == 0
    assert report["recovery_rate"] == pytest.approx(0.0)


# --- 6. per-family rates and covered families ---------------------------------


def test_per_family_rates_accumulate_across_scenarios():
    scenarios = [
        _scenario(scenario_id="flat-ok"),
        _scenario(scenario_id="flat-bad", expected_claim_statuses={"auc": "diverged"}),
        _scenario(
            scenario_id="json-ok",
            claims=[{"id": "j1", "value": 0.9, "from": "results.json", "path": "auc"}],
            expected_claim_statuses={"j1": "reproduced"},
        ),
    ]
    report = evaluate_reproduce(scenarios, run_started_at=_RUN_START)

    flat = report["per_family"]["flat"]
    assert isinstance(flat, FamilyScore)
    assert flat.matched == 1
    assert flat.total == 2
    assert flat.rate == pytest.approx(0.5)

    json_family = report["per_family"]["json"]
    assert json_family.matched == 1
    assert json_family.total == 1
    assert json_family.rate == pytest.approx(1.0)


def test_covered_families_sorted_and_exhaustive():
    report = evaluate_reproduce(
        [
            _scenario(scenario_id="flat"),
            _scenario(
                scenario_id="json",
                claims=[{"id": "j1", "value": 0.9, "from": "results.json", "path": "auc"}],
                expected_claim_statuses={"j1": "reproduced"},
            ),
        ],
        run_started_at=_RUN_START,
    )
    assert report["covered_families"] == ["flat", "json"]


# --- 7. snapshot_from_reproduce_report ----------------------------------------


def test_snapshot_projects_report_fields_with_injected_timestamp():
    report = evaluate_reproduce([_scenario()], run_started_at=_RUN_START)
    snapshot = snapshot_from_reproduce_report(
        report,
        corpus_sha="sha-seed",
        contig_version="0.54.0",
        timestamp="2026-08-14T00:00:00+00:00",
    )
    assert snapshot.timestamp == "2026-08-14T00:00:00+00:00"
    assert snapshot.scenario_count == report["total_count"]
    assert snapshot.corpus_sha == "sha-seed"
    assert snapshot.outcome_match_rate == pytest.approx(report["outcome_match_rate"])
    assert snapshot.recovery_rate == pytest.approx(report["recovery_rate"])
    assert snapshot.per_family == report["per_family"]
    assert snapshot.covered_families == ["flat"]
    assert snapshot.contig_version == "0.54.0"


def test_snapshot_timestamp_defaults_to_now_utc():
    report = evaluate_reproduce([_scenario()], run_started_at=_RUN_START)
    snapshot = snapshot_from_reproduce_report(
        report, corpus_sha="sha-seed", contig_version="0.54.0"
    )
    parsed = datetime.fromisoformat(snapshot.timestamp)
    assert parsed.tzinfo is not None
    assert snapshot.timestamp.endswith("+00:00")


# --- 8. baseline save/load ----------------------------------------------------


def test_save_and_load_baseline_round_trip(tmp_path):
    path = tmp_path / "baseline.json"
    assert load_reproduce_baseline(path) is None  # missing file -> None

    snapshot = _snapshot(0.9)
    save_reproduce_baseline(snapshot, path)
    assert load_reproduce_baseline(path) == snapshot

    # One pretty-printed JSON object, NOT JSONL.
    text = path.read_text()
    parsed = json.loads(text)
    assert parsed == snapshot.model_dump()


# --- 9. compare_reproduce_to_baseline -----------------------------------------


def test_compare_regression_below_baseline_minus_tolerance():
    status, message = compare_reproduce_to_baseline(
        _snapshot(0.8), _snapshot(0.9), tolerance=1e-9
    )
    assert status == "regressed"
    assert "REGRESSION" in message
    assert "corpus sha mismatch" not in message
    assert "contig version mismatch" not in message


def test_compare_improvement_above_baseline_plus_tolerance():
    status, message = compare_reproduce_to_baseline(
        _snapshot(0.9), _snapshot(0.8), tolerance=1e-9
    )
    assert status == "improved"
    assert "improved" in message


def test_compare_equal_rate_is_pass():
    status, message = compare_reproduce_to_baseline(
        _snapshot(0.9), _snapshot(0.9), tolerance=1e-9
    )
    assert status == "pass"
    assert "PASS" in message


def test_compare_default_tolerance_absorbs_float_noise():
    # Mirrors verify-guard's CLI default (1e-9): a hair below baseline is not
    # a regression.
    status, _ = compare_reproduce_to_baseline(_snapshot(0.9 - 5e-10), _snapshot(0.9))
    assert status == "pass"


def test_compare_sha_mismatch_is_informational_only():
    status, message = compare_reproduce_to_baseline(
        _snapshot(0.9, corpus_sha="sha-new"),
        _snapshot(0.9, corpus_sha="sha-old"),
        tolerance=1e-9,
    )
    assert status == "pass"  # rate unchanged: informational warning only
    assert "corpus sha mismatch" in message


def test_compare_sha_mismatch_does_not_mask_a_regression():
    status, message = compare_reproduce_to_baseline(
        _snapshot(0.8, corpus_sha="sha-new"),
        _snapshot(0.9, corpus_sha="sha-old"),
        tolerance=1e-9,
    )
    assert status == "regressed"  # rate comparison still decides
    assert "corpus sha mismatch" in message


def test_compare_version_mismatch_is_informational_only():
    status, message = compare_reproduce_to_baseline(
        _snapshot(0.9, version="0.54.0"),
        _snapshot(0.9, version="0.53.0"),
        tolerance=1e-9,
    )
    assert status == "pass"
    assert "contig version mismatch" in message


# --- 10. load_reproduce_scenarios ---------------------------------------------


def test_load_reproduce_scenarios_skips_malformed_lines(tmp_path):
    good = _scenario(scenario_id="a")
    path = tmp_path / "scenarios.jsonl"
    path.write_text(
        f"\n{good.model_dump_json()}\nnot json at all\n\n{good.model_dump_json()}\n"
    )
    scenarios = load_reproduce_scenarios(path)
    assert len(scenarios) == 2
    assert scenarios[0].scenario_id == "a"
