"""CLI tests for `contig reproduce-guard` (C6 fold-in: the reproduce regression guard).

Mirrors tests/test_verify_guard.py (itself the mirror of
tests/test_cli_heal_guard.py), but for the reproduce loop's per-scenario
outcome-match rate over the frozen synthetic scenario set instead of the
verification rules' verdict-match rate. Every history/baseline path here is
isolated under tmp_path so no test touches the committed
reproduce_baseline.json/reproduce_history.jsonl -- the committed-baseline bare
test (test_reproduce_guard_default_committed_baseline_passes_clean) is the one
deliberate exception, the same boundary test_verify_guard.py draws.
"""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from contig.cli import app
from contig.models import ReproduceSnapshot
from contig.reproduce_guard import (
    default_reproduce_scenarios_path,
    load_reproduce_baseline,
)
from contig.snapshot_history import append_jsonl, load_jsonl

runner = CliRunner()


def _perturb_one_expected(tmp_path):
    """Copy the shipped scenarios but flip `flat-exact`'s expected c1 status to
    "diverged" -- the current replay reproduces it exactly, so this
    deterministically drops the outcome-match rate below the baseline
    (16/17 -> 15/17) and forces a REGRESSION that names the scenario id."""
    lines = default_reproduce_scenarios_path().read_text().splitlines()
    perturbed_lines = []
    for line in lines:
        if not line.strip():
            continue
        obj = json.loads(line)
        if obj["scenario_id"] == "flat-exact":
            obj["expected_claim_statuses"]["c1"] = "diverged"
        perturbed_lines.append(json.dumps(obj))

    path = tmp_path / "perturbed.jsonl"
    path.write_text("\n".join(perturbed_lines) + "\n")
    return path


def _freeze(tmp_path, **over):
    """Run --update-baseline against the committed scenarios into tmp files."""
    baseline_path = tmp_path / "baseline.json"
    history_path = tmp_path / "history.jsonl"
    args = ["reproduce-guard", "--update-baseline", "--baseline", str(baseline_path),
            "--history-file", str(history_path)]
    for flag, value in over.items():
        args += [flag, str(value)]
    freeze = runner.invoke(app, args)
    assert freeze.exit_code == 0
    return baseline_path, history_path


def _seed_history(tmp_path, n_points: int):
    history_path = tmp_path / "reproduce_history.jsonl"
    for i in range(n_points):
        append_jsonl(
            ReproduceSnapshot(
                timestamp=f"2026-08-0{i + 1}T00:00:00+00:00",
                scenario_count=14,
                corpus_sha="sha-a",
                outcome_match_rate=0.90 + 0.05 * i,
                recovery_rate=0.0,
                per_family=None,
                covered_families=["flat"],
                contig_version="0.39.0",
            ),
            history_path,
        )
    return history_path


# --- (a) default invocation: the REAL shipped corpus + committed baseline -----


def test_reproduce_guard_default_committed_baseline_passes_clean():
    """The real entry point: `contig reproduce-guard` (no args) must pass
    against the committed baseline + shipped synthetic scenarios, printing the
    rate and naming the one deliberate known-miss -- locks 'committed baseline
    sha == shipped scenarios sha' so a future corpus edit without
    --update-baseline cannot silently rot the guard."""
    result = runner.invoke(app, ["reproduce-guard"])
    assert result.exit_code == 0
    assert "reproduce-guard PASS" in result.output
    assert "94.1%" in result.output  # 16/17, the shipped rate
    assert "known-miss" in result.output  # the deliberate mismatch, named
    assert "flat" in result.output  # per-family rendering


# --- (b) a perturbed corpus regresses against the committed baseline ----------


def test_reproduce_guard_regression_on_perturbed_scenario(tmp_path):
    perturbed = _perturb_one_expected(tmp_path)

    # --scenarios points at the mutated copy; --baseline stays the SHIPPED
    # baseline, so the corpus_sha mismatch fires as well -- and the regression
    # exit must be driven by the rate drop, with the sha warning informational
    # (the REGRESSION message still stands).
    guard = runner.invoke(app, ["reproduce-guard", "--scenarios", str(perturbed)])

    assert guard.exit_code == 1
    assert "REGRESSION" in guard.output
    assert "flat-exact" in guard.output
    assert "sha" in guard.output.lower()  # informational sha warning, present
    assert "94.1%" in guard.output  # the baseline rate in the summary


# --- (c) --json emits the snapshot as parseable JSON ---------------------------


def test_reproduce_guard_json(tmp_path):
    baseline_path, _ = _freeze(tmp_path)

    guard = runner.invoke(app, ["reproduce-guard", "--baseline", str(baseline_path), "--json"])
    assert guard.exit_code == 0
    parsed = json.loads(guard.output)
    assert parsed["scenario_count"] == 17
    assert parsed["outcome_match_rate"] == pytest.approx(16 / 17)
    assert parsed["outcome_match_rate"] < 1.0  # the known-miss keeps it below 1.0


# --- (d) --update-baseline rewrites the baseline and appends history ----------


def test_reproduce_guard_update_baseline_writes_and_plain_guard_does_not(tmp_path):
    baseline_path, history_path = _freeze(tmp_path)

    baseline = load_reproduce_baseline(baseline_path)
    assert baseline is not None
    assert baseline.outcome_match_rate == pytest.approx(16 / 17)
    assert len(load_jsonl(ReproduceSnapshot, history_path)) == 1

    before_mtime = baseline_path.stat().st_mtime_ns
    before_content = baseline_path.read_text()

    guard = runner.invoke(app, ["reproduce-guard", "--baseline", str(baseline_path)])
    assert guard.exit_code == 0
    assert baseline_path.stat().st_mtime_ns == before_mtime
    assert baseline_path.read_text() == before_content


def test_reproduce_guard_update_baseline_message(tmp_path):
    baseline_path, _ = _freeze(tmp_path)

    freeze = runner.invoke(
        app,
        ["reproduce-guard", "--update-baseline", "--baseline", str(baseline_path),
         "--history-file", str(tmp_path / "history.jsonl")],
    )
    assert freeze.exit_code == 0
    assert "Baseline updated" in freeze.output
    assert "94.1%" in freeze.output


# --- (e) missing scenarios file: loud failure, mirroring verify-guard ---------


def test_reproduce_guard_missing_scenarios_file(tmp_path):
    missing = tmp_path / "does_not_exist.jsonl"

    result = runner.invoke(app, ["reproduce-guard", "--scenarios", str(missing)])

    assert result.exit_code == 1
    assert "not found" in result.output.lower()


# --- (f) --snapshot appends history without touching the baseline --------------


def test_reproduce_guard_snapshot_only_appends_history(tmp_path):
    baseline_path, history_path = _freeze(tmp_path)
    baseline_before = baseline_path.read_text()
    assert len(load_jsonl(ReproduceSnapshot, history_path)) == 1  # from the freeze

    snapshotted = runner.invoke(
        app,
        ["reproduce-guard", "--baseline", str(baseline_path), "--snapshot",
         "--history-file", str(history_path)],
    )
    assert snapshotted.exit_code == 0
    assert baseline_path.read_text() == baseline_before  # baseline bytes untouched
    snaps = load_jsonl(ReproduceSnapshot, history_path)
    assert len(snaps) == 2


# --- (g) --history prints the trend; --history-file overrides ------------------


def test_reproduce_guard_history_prints_trend(tmp_path):
    history_path = _seed_history(tmp_path, 2)

    result = runner.invoke(
        app, ["reproduce-guard", "--history", "--history-file", str(history_path)]
    )
    assert result.exit_code == 0
    assert "Reproduce outcome-match over time" in result.output
    assert "90.0%" in result.output
    assert "95.0%" in result.output
    assert "+5.0pp" in result.output
    assert "←latest" in result.output


def test_reproduce_guard_history_empty_note(tmp_path):
    history_path = tmp_path / "does_not_exist.jsonl"
    result = runner.invoke(
        app, ["reproduce-guard", "--history", "--history-file", str(history_path)]
    )
    assert result.exit_code == 0
    assert "No reproduce outcome-match snapshots recorded yet" in result.output


def test_reproduce_guard_history_json(tmp_path):
    history_path = _seed_history(tmp_path, 2)

    result = runner.invoke(
        app, ["reproduce-guard", "--history", "--json", "--history-file", str(history_path)]
    )
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert isinstance(data, list)
    assert len(data) == 2
    assert data[1]["outcome_match_rate"] == pytest.approx(0.95)


# --- (h) --update-baseline never exits non-zero (deliberate-refreeze contract) -


def test_reproduce_guard_update_baseline_never_fails_even_on_mutated_corpus(tmp_path):
    perturbed = _perturb_one_expected(tmp_path)
    baseline_path = tmp_path / "baseline.json"
    history_path = tmp_path / "history.jsonl"

    freeze = runner.invoke(
        app,
        ["reproduce-guard", "--scenarios", str(perturbed), "--update-baseline",
         "--baseline", str(baseline_path), "--history-file", str(history_path)],
    )
    assert freeze.exit_code == 0
    assert "Baseline updated" in freeze.output

    baseline = load_reproduce_baseline(baseline_path)
    assert baseline is not None
    assert baseline.outcome_match_rate == pytest.approx(15 / 17)
    assert len(load_jsonl(ReproduceSnapshot, history_path)) == 1
