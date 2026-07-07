"""CLI tests for `contig heal-guard` (C6 slice 2: the self-heal regression guard).

Mirrors tests/test_eval_holdout.py's Phase C (`eval-guard` CLI tests), but for
the self-heal loop's outcome-match rate over the frozen synthetic scenario set
instead of detector accuracy over a held-out corpus.
"""

from __future__ import annotations

import json

from typer.testing import CliRunner

from contig.cli import app
from contig.heal import default_heal_baseline_path, default_heal_scenarios_path
from contig.models import HealGuardResult

runner = CliRunner()


def _perturb_tool_crash_giveup(tmp_path):
    """Copy the shipped scenario set but flip `tool-crash-giveup`'s declared
    outcome to a healed one it never reaches (it only has a single FAILED
    attempt, so the real loop still gives up) -- this deterministically drops
    the corpus outcome-match rate below the shipped baseline's 1.0."""
    lines = default_heal_scenarios_path().read_text().splitlines()
    perturbed_lines = []
    for line in lines:
        if not line.strip():
            continue
        obj = json.loads(line)
        if obj["scenario_id"] == "tool-crash-giveup":
            obj["expected_recovered"] = True
            obj["expected_outcome"] = "patched_and_retried"
        perturbed_lines.append(json.dumps(obj))

    path = tmp_path / "scenarios.jsonl"
    path.write_text("\n".join(perturbed_lines) + "\n")
    return path


# --- (a) shipped set passes clean, human summary --------------------------


def test_heal_guard_default_committed_baseline_passes_clean():
    result = runner.invoke(app, ["heal-guard"])
    assert result.exit_code == 0
    assert "outcome-match 100%" in result.output
    assert "synthetic" in result.output


# --- (b) --json emits parseable HealGuardResult -----------------------------


def test_heal_guard_json():
    result = runner.invoke(app, ["heal-guard", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    parsed = HealGuardResult.model_validate(data)
    assert parsed.has_baseline is True
    assert parsed.regressed is False


# --- (c) a perturbed scenario regresses against the shipped baseline -------


def test_heal_guard_regression_on_perturbed_scenario(tmp_path):
    scenarios_path = _perturb_tool_crash_giveup(tmp_path)

    guard = runner.invoke(
        app,
        [
            "heal-guard",
            "--scenarios", str(scenarios_path),
            "--baseline", str(default_heal_baseline_path()),
        ],
    )

    assert guard.exit_code == 1
    assert "REGRESSION" in guard.output
    assert "tool-crash-giveup" in guard.output


# --- (d) --update-baseline writes the file; a plain guard does not ---------


def test_heal_guard_update_baseline_writes_and_plain_guard_does_not(tmp_path):
    baseline_path = tmp_path / "baseline.json"

    freeze = runner.invoke(app, ["heal-guard", "--update-baseline", "--baseline", str(baseline_path)])
    assert freeze.exit_code == 0
    assert baseline_path.exists()

    before_mtime = baseline_path.stat().st_mtime_ns
    before_content = baseline_path.read_text()

    guard = runner.invoke(app, ["heal-guard", "--baseline", str(baseline_path)])
    assert guard.exit_code == 0

    assert baseline_path.stat().st_mtime_ns == before_mtime
    assert baseline_path.read_text() == before_content


def test_heal_guard_update_baseline_message():
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as d:
        baseline_path = Path(d) / "baseline.json"
        freeze = runner.invoke(app, ["heal-guard", "--update-baseline", "--baseline", str(baseline_path)])
        assert freeze.exit_code == 0
        assert "Baseline updated" in freeze.output
        assert "synthetic" in freeze.output


# --- (e) missing baseline, no --update-baseline -----------------------------


def test_heal_guard_no_baseline(tmp_path):
    baseline_path = tmp_path / "does_not_exist.json"

    guard = runner.invoke(app, ["heal-guard", "--baseline", str(baseline_path)])

    assert guard.exit_code == 1
    assert "--update-baseline" in guard.output


def test_heal_guard_missing_scenarios_file(tmp_path):
    missing = tmp_path / "does_not_exist.jsonl"

    result = runner.invoke(app, ["heal-guard", "--scenarios", str(missing)])

    assert result.exit_code == 1
    assert "not found" in result.output.lower()
