"""Tests for the self-heal regression guard's I/O + pure compare (C6 slice 2).

Mirrors tests/test_eval_holdout.py's Phase B (baseline record + pure
comparator), but for the self-heal loop's outcome-match rate instead of
detector accuracy: `compare_heal_to_baseline` decides regressed/improved
without touching disk, and `save_heal_baseline`/`load_heal_baseline` round-trip
the committed baseline artifact.
"""

from __future__ import annotations

import pytest

from contig.heal import (
    compare_heal_to_baseline,
    default_heal_baseline_path,
    default_heal_scenarios_path,
    load_heal_baseline,
    load_heal_scenarios,
    save_heal_baseline,
    snapshot_from_heal_report,
)
from contig.models import HealClassScore, HealEvalReport, HealScenarioResult, HealSnapshot


def _report(
    outcome_match_rate: float,
    *,
    recovery_rate: float = 0.5,
    mismatches: list[HealScenarioResult] | None = None,
) -> HealEvalReport:
    return HealEvalReport(
        total=10,
        matched=round(outcome_match_rate * 10),
        outcome_match_rate=outcome_match_rate,
        healed=round(recovery_rate * 10),
        recovery_rate=recovery_rate,
        per_class={},
        mismatches=mismatches or [],
    )


def _baseline(
    outcome_match_rate: float,
    *,
    corpus_sha: str = "sha-a",
    recovery_rate: float = 0.5,
) -> HealSnapshot:
    return HealSnapshot(
        timestamp="2026-07-01T00:00:00+00:00",
        scenario_count=10,
        corpus_sha=corpus_sha,
        outcome_match_rate=outcome_match_rate,
        recovery_rate=recovery_rate,
        per_class={},
        covered_classes=["oom", "time_limit"],
        contig_version="0.21.0",
    )


# --- default paths -----------------------------------------------------------


def test_default_paths_differ_and_named_correctly():
    assert default_heal_scenarios_path() != default_heal_baseline_path()
    assert default_heal_scenarios_path().name == "heal_scenarios.jsonl"
    assert default_heal_baseline_path().name == "heal_baseline.json"


# --- load_heal_scenarios ------------------------------------------------------


def test_load_heal_scenarios_skips_blank_lines(tmp_path):
    path = tmp_path / "scenarios.jsonl"
    scenario_json = (
        '{"scenario_id": "s1", "description": "d", "source": "synthetic", '
        '"expected_class": "oom", "attempts": [{"status": "FAILED", "exit": 137, '
        '"log_text": "oom"}], "expected_recovered": true, "expected_outcome": "healed"}'
    )
    path.write_text(f"\n{scenario_json}\n\n{scenario_json}\n")

    scenarios = load_heal_scenarios(path)

    assert len(scenarios) == 2
    assert scenarios[0].scenario_id == "s1"
    assert scenarios[0].expected_class == "oom"


# --- compare_heal_to_baseline (pure) ------------------------------------------


def test_compare_no_baseline():
    result = compare_heal_to_baseline(
        _report(0.5), baseline=None, corpus_sha="sha-a", tolerance=1e-9
    )
    assert result.has_baseline is False
    assert result.regressed is False
    assert result.improved is False
    assert result.baseline_match_rate is None
    assert result.delta is None
    assert result.baseline_sha is None
    assert result.sha_mismatch is False
    assert result.outcome_match_rate == pytest.approx(0.5)
    assert result.corpus_sha == "sha-a"


def test_compare_equal_rate():
    baseline = _baseline(0.9)
    result = compare_heal_to_baseline(
        _report(0.9), baseline=baseline, corpus_sha="sha-a", tolerance=1e-9
    )
    assert result.regressed is False
    assert result.improved is False
    assert result.has_baseline is True
    assert result.baseline_match_rate == pytest.approx(0.9)
    assert result.delta == pytest.approx(0.0)
    assert result.sha_mismatch is False


def test_compare_below_baseline_minus_tolerance_regresses():
    baseline = _baseline(0.9)
    result = compare_heal_to_baseline(
        _report(0.5), baseline=baseline, corpus_sha="sha-a", tolerance=1e-9
    )
    assert result.regressed is True
    assert result.improved is False
    assert result.delta < 0


def test_compare_above_baseline_plus_tolerance_improves():
    baseline = _baseline(0.5)
    result = compare_heal_to_baseline(
        _report(0.9), baseline=baseline, corpus_sha="sha-a", tolerance=1e-9
    )
    assert result.improved is True
    assert result.regressed is False
    assert result.delta > 0


def test_compare_tolerance_absorbs_float_noise():
    baseline = _baseline(0.9)
    result = compare_heal_to_baseline(
        _report(0.9 - 0.05), baseline=baseline, corpus_sha="sha-a", tolerance=0.1
    )
    assert result.regressed is False


def test_compare_sha_mismatch():
    baseline = _baseline(0.9, corpus_sha="sha-old")
    result = compare_heal_to_baseline(
        _report(0.9), baseline=baseline, corpus_sha="sha-new", tolerance=1e-9
    )
    assert result.sha_mismatch is True
    assert result.baseline_sha == "sha-old"


def test_compare_carries_mismatches_through():
    mismatches = [
        HealScenarioResult(
            scenario_id="s1",
            diagnosed_class="oom",
            recovered=False,
            actual_outcome="gave_up",
            matched=False,
            divergence=["outcome: expected 'healed', got 'gave_up'"],
        )
    ]
    baseline = _baseline(0.9)
    result = compare_heal_to_baseline(
        _report(0.9, mismatches=mismatches),
        baseline=baseline,
        corpus_sha="sha-a",
        tolerance=1e-9,
    )
    assert result.mismatches == mismatches


# --- save/load baseline round-trip --------------------------------------------


def test_baseline_roundtrip(tmp_path):
    path = tmp_path / "baseline.json"
    assert load_heal_baseline(path) is None  # missing file -> None, not an error

    snapshot = _baseline(0.9)
    save_heal_baseline(snapshot, path)
    loaded = load_heal_baseline(path)

    assert loaded == snapshot


# --- snapshot_from_heal_report -------------------------------------------------


def test_snapshot_from_heal_report_uses_passed_in_timestamp():
    report = _report(0.8, recovery_rate=0.4)
    snapshot = snapshot_from_heal_report(
        report,
        corpus_sha="sha-x",
        covered_classes=["oom", "tool_crash"],
        contig_version="0.21.0",
        timestamp="2026-07-07T00:00:00+00:00",
    )

    assert snapshot.timestamp == "2026-07-07T00:00:00+00:00"
    assert snapshot.scenario_count == report.total
    assert snapshot.corpus_sha == "sha-x"
    assert snapshot.outcome_match_rate == pytest.approx(0.8)
    assert snapshot.recovery_rate == pytest.approx(0.4)
    assert snapshot.covered_classes == ["oom", "tool_crash"]
    assert snapshot.contig_version == "0.21.0"
