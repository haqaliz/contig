"""CLI tests for `contig verify-guard` (C6 fold-in: the verification regression guard).

Mirrors tests/test_cli_heal_guard.py and tests/test_guard_trend.py, but for
the verification rules' verdict-match rate over the frozen synthetic holdout
instead of the self-heal loop's outcome-match rate. Every history/baseline
path here is isolated under tmp_path so no test touches the committed
verify_baseline.json/verify_history.jsonl (the committed-baseline bare test
lives in test_guard_trend.py, where the deliberate baseline freeze in aspect-2
Phase 2 made it possible).
"""

from __future__ import annotations

import json

from typer.testing import CliRunner

from contig.cli import app
from contig.models import VerifyGuardResult, VerifySnapshot
from contig.snapshot_history import append_jsonl, load_jsonl
from contig.verify_corpus import default_verify_holdout_path

runner = CliRunner()


def _perturb_one_label(tmp_path):
    """Copy the shipped holdout but flip `verify-germline-ts-tv-pass`'s label to
    "fail" -- the current bands PASS that case, so this deterministically drops
    the verdict-match rate below the baseline (21/22 -> 20/22) and forces a
    REGRESSION that names the case id."""
    lines = default_verify_holdout_path().read_text().splitlines()
    perturbed_lines = []
    for line in lines:
        if not line.strip():
            continue
        obj = json.loads(line)
        if obj["case_id"] == "verify-germline-ts-tv-pass":
            obj["expected_verdict"] = "fail"
        perturbed_lines.append(json.dumps(obj))

    path = tmp_path / "holdout.jsonl"
    path.write_text("\n".join(perturbed_lines) + "\n")
    return path


def _freeze(tmp_path, **over):
    """Run --update-baseline against the committed holdout into tmp files."""
    baseline_path = tmp_path / "baseline.json"
    history_path = tmp_path / "history.jsonl"
    args = ["verify-guard", "--update-baseline", "--baseline", str(baseline_path),
            "--history-file", str(history_path)]
    for flag, value in over.items():
        args += [flag, str(value)]
    freeze = runner.invoke(app, args)
    assert freeze.exit_code == 0
    return baseline_path, history_path


# --- (a) tmp baseline passes clean, human summary ---------------------------


def test_verify_guard_default_committed_baseline_passes_clean():
    """The real entry point: `contig verify-guard` (no args) must pass against
    the committed baseline + shipped synthetic holdout, with no spurious sha
    warning -- locks 'committed baseline sha == shipped holdout sha' so a
    future holdout edit without --update-baseline cannot silently rot the
    guard."""
    result = runner.invoke(app, ["verify-guard"])
    assert result.exit_code == 0
    assert "verify-guard PASS" in result.output
    assert "verdict-match 95.5%" in result.output
    assert "changed" not in result.output.lower()  # no holdout-sha mismatch


def test_verify_guard_passes_clean_against_tmp_baseline(tmp_path):
    baseline_path, _ = _freeze(tmp_path)

    guard = runner.invoke(app, ["verify-guard", "--baseline", str(baseline_path)])
    assert guard.exit_code == 0
    assert "verify-guard PASS" in guard.output
    assert "verdict-match 95.5%" in guard.output


# --- (b) --json emits parseable VerifyGuardResult ----------------------------


def test_verify_guard_json(tmp_path):
    baseline_path, _ = _freeze(tmp_path)

    guard = runner.invoke(app, ["verify-guard", "--baseline", str(baseline_path), "--json"])
    assert guard.exit_code == 0
    parsed = VerifyGuardResult.model_validate(json.loads(guard.output))
    assert parsed.has_baseline is True
    assert parsed.regressed is False
    assert parsed.verdict_match_rate < 1.0  # the known-miss keeps it below 1.0


# --- (c) a perturbed corpus regresses against the baseline ------------------


def test_verify_guard_regression_on_perturbed_case(tmp_path):
    perturbed = _perturb_one_label(tmp_path)
    baseline_path, _ = _freeze(tmp_path)

    guard = runner.invoke(
        app,
        ["verify-guard", "--corpus", str(perturbed), "--baseline", str(baseline_path)],
    )

    assert guard.exit_code == 1
    assert "REGRESSION" in guard.output
    assert "verify-germline-ts-tv-pass" in guard.output


# --- (d) --update-baseline writes the file; a plain guard does not -----------


def test_verify_guard_update_baseline_writes_and_plain_guard_does_not(tmp_path):
    baseline_path, history_path = _freeze(tmp_path)

    before_mtime = baseline_path.stat().st_mtime_ns
    before_content = baseline_path.read_text()

    guard = runner.invoke(app, ["verify-guard", "--baseline", str(baseline_path)])
    assert guard.exit_code == 0

    assert baseline_path.stat().st_mtime_ns == before_mtime
    assert baseline_path.read_text() == before_content


def test_verify_guard_update_baseline_message(tmp_path):
    baseline_path, _ = _freeze(tmp_path)
    freeze = runner.invoke(app, ["verify-guard", "--update-baseline", "--baseline", str(baseline_path)])
    assert freeze.exit_code == 0
    assert "Baseline updated" in freeze.output
    assert "verdict-match 95.5%" in freeze.output


# --- (e) missing baseline / missing corpus ------------------------------------


def test_verify_guard_no_baseline(tmp_path):
    baseline_path = tmp_path / "does_not_exist.json"

    guard = runner.invoke(app, ["verify-guard", "--baseline", str(baseline_path)])

    assert guard.exit_code == 1
    assert "--update-baseline" in guard.output


def test_verify_guard_missing_corpus_file(tmp_path):
    missing = tmp_path / "does_not_exist.jsonl"

    result = runner.invoke(app, ["verify-guard", "--corpus", str(missing)])

    assert result.exit_code == 1
    assert "not found" in result.output.lower()


# --- (f) --snapshot appends history without touching the baseline -------------


def test_verify_guard_snapshot_only_appends_history(tmp_path):
    baseline_path, history_path = _freeze(tmp_path)
    baseline_before = baseline_path.read_text()
    assert len(load_jsonl(VerifySnapshot, history_path)) == 1  # from the freeze

    snapshotted = runner.invoke(
        app,
        ["verify-guard", "--baseline", str(baseline_path), "--snapshot",
         "--history-file", str(history_path)],
    )
    assert snapshotted.exit_code == 0
    assert baseline_path.read_text() == baseline_before  # baseline untouched
    snaps = load_jsonl(VerifySnapshot, history_path)
    assert len(snaps) == 2


# --- (g) --history prints the trend --------------------------------------------


def _seed_history(tmp_path, n_points: int) -> object:
    history_path = tmp_path / "verify_history.jsonl"
    for i in range(n_points):
        append_jsonl(
            VerifySnapshot(
                timestamp=f"2026-08-0{i + 1}T00:00:00+00:00",
                case_count=22,
                corpus_sha="sha-a",
                verdict_match_rate=0.90 + 0.05 * i,
                contig_version="0.39.0",
            ),
            history_path,
        )
    return history_path


def test_verify_guard_history_prints_trend(tmp_path):
    history_path = _seed_history(tmp_path, 2)

    result = runner.invoke(
        app, ["verify-guard", "--history", "--history-file", str(history_path)]
    )
    assert result.exit_code == 0
    assert "Verification verdict-match over time" in result.output
    assert "90.0%" in result.output
    assert "95.0%" in result.output
    assert "+5.0pp" in result.output
    assert "←latest" in result.output


def test_verify_guard_history_empty_note(tmp_path):
    history_path = tmp_path / "does_not_exist.jsonl"
    result = runner.invoke(
        app, ["verify-guard", "--history", "--history-file", str(history_path)]
    )
    assert result.exit_code == 0
    assert "No verification verdict-match snapshots recorded yet" in result.output


def test_verify_guard_history_json(tmp_path):
    history_path = _seed_history(tmp_path, 2)

    result = runner.invoke(
        app, ["verify-guard", "--history", "--json", "--history-file", str(history_path)]
    )
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert isinstance(data, list)
    assert len(data) == 2


# --- (h) sha mismatch warns but does not fail by itself ------------------------


def test_verify_guard_sha_mismatch_warns_not_fails(tmp_path):
    perturbed = _perturb_one_label(tmp_path)
    baseline_path, _ = _freeze(tmp_path)

    # The perturbed corpus re-labels a case, so the sha differs from the
    # baseline's; the guard must WARN about it, and let the regression logic
    # decide the exit code (here: the rate also drops, so it exits 1 -- but the
    # warning is the sha mismatch, asserted separately).
    guard = runner.invoke(
        app, ["verify-guard", "--corpus", str(perturbed), "--baseline", str(baseline_path)]
    )
    assert "changed" in guard.output.lower()
    assert "sha" in guard.output.lower()
    assert guard.exit_code == 1  # the regression, not the sha mismatch, exits 1

    # A perturbed corpus that keeps the rate (re-label the known-miss, which
    # still mismatches) must warn about the sha but still PASS, proving the
    # mismatch alone never fails the guard.
    lines = default_verify_holdout_path().read_text().splitlines()
    perturbed_lines = []
    for line in lines:
        if not line.strip():
            continue
        obj = json.loads(line)
        if obj["case_id"] == "verify-germline-known-miss":
            obj["expected_verdict"] = "pass"  # still != predicted "fail" -> still 21/22
        perturbed_lines.append(json.dumps(obj))
    rate_same = tmp_path / "rate_same.jsonl"
    rate_same.write_text("\n".join(perturbed_lines) + "\n")

    guard = runner.invoke(
        app, ["verify-guard", "--corpus", str(rate_same), "--baseline", str(baseline_path)]
    )
    assert "changed" in guard.output.lower()
    assert guard.exit_code == 0
