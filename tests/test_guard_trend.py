"""CLI tests for the guard-cli aspect (C6, aspect 2): `--snapshot`/`--history`/
`--history-file` on `eval-guard` and `heal-guard`, mirroring the shipped
`eval-detector --snapshot/--history` (tests/test_cli.py). Every history/
baseline path is isolated under tmp_path -- no test touches the committed
holdout_history.jsonl/heal_history.jsonl or their baselines.
"""

from __future__ import annotations

import json

from typer.testing import CliRunner

from contig.cli import app
from contig.heal import default_heal_baseline_path, default_heal_scenarios_path
from contig.holdout import default_baseline_path, default_holdout_path
from contig.models import EvalSnapshot, HealSnapshot
from contig.snapshot_history import append_jsonl, load_jsonl

runner = CliRunner()


# --- eval-guard --------------------------------------------------------------


def test_eval_guard_bare_writes_no_history(tmp_path):
    baseline_path = tmp_path / "baseline.json"
    history_path = tmp_path / "holdout_history.jsonl"
    setup_history_path = tmp_path / "setup_history.jsonl"

    freeze = runner.invoke(
        app,
        ["eval-guard", "--update-baseline", "--baseline", str(baseline_path),
         "--history-file", str(setup_history_path)],
    )
    assert freeze.exit_code == 0

    result = runner.invoke(
        app,
        [
            "eval-guard",
            "--baseline", str(baseline_path),
            "--history-file", str(history_path),
        ],
    )
    assert result.exit_code == 0
    assert not history_path.exists()


def test_eval_guard_snapshot_appends_one(tmp_path):
    baseline_path = tmp_path / "baseline.json"
    history_path = tmp_path / "holdout_history.jsonl"
    setup_history_path = tmp_path / "setup_history.jsonl"

    freeze = runner.invoke(
        app,
        ["eval-guard", "--update-baseline", "--baseline", str(baseline_path),
         "--history-file", str(setup_history_path)],
    )
    assert freeze.exit_code == 0

    bare = runner.invoke(app, ["eval-guard", "--baseline", str(baseline_path)])

    snapshotted = runner.invoke(
        app,
        [
            "eval-guard",
            "--baseline", str(baseline_path),
            "--snapshot",
            "--history-file", str(history_path),
        ],
    )
    assert snapshotted.exit_code == bare.exit_code
    snaps = load_jsonl(EvalSnapshot, history_path)
    assert len(snaps) == 1


def test_eval_guard_update_baseline_appends_one(tmp_path):
    baseline_path = tmp_path / "baseline.json"
    history_path = tmp_path / "holdout_history.jsonl"

    first = runner.invoke(
        app,
        [
            "eval-guard",
            "--update-baseline",
            "--baseline", str(baseline_path),
            "--history-file", str(history_path),
        ],
    )
    assert first.exit_code == 0
    assert baseline_path.exists()
    assert len(load_jsonl(EvalSnapshot, history_path)) == 1

    second = runner.invoke(
        app,
        [
            "eval-guard",
            "--update-baseline",
            "--baseline", str(baseline_path),
            "--history-file", str(history_path),
        ],
    )
    assert second.exit_code == 0
    assert len(load_jsonl(EvalSnapshot, history_path)) == 2


def test_eval_guard_history_renders_delta(tmp_path):
    history_path = tmp_path / "holdout_history.jsonl"
    append_jsonl(
        EvalSnapshot(
            timestamp="2026-07-01T00:00:00+00:00",
            corpus_size=10,
            corpus_sha="sha-a",
            accuracy=0.80,
            contig_version="0.38.0",
            detector="rules",
        ),
        history_path,
    )
    append_jsonl(
        EvalSnapshot(
            timestamp="2026-07-10T00:00:00+00:00",
            corpus_size=10,
            corpus_sha="sha-a",
            accuracy=0.90,
            contig_version="0.39.0",
            detector="rules",
        ),
        history_path,
    )

    result = runner.invoke(
        app, ["eval-guard", "--history", "--history-file", str(history_path)]
    )
    assert result.exit_code == 0
    assert "accuracy 80.0%" in result.output
    assert "accuracy 90.0%" in result.output
    assert "+10.0pp" in result.output
    assert "←latest" in result.output


def test_eval_guard_history_empty_note(tmp_path):
    history_path = tmp_path / "does_not_exist.jsonl"
    result = runner.invoke(
        app, ["eval-guard", "--history", "--history-file", str(history_path)]
    )
    assert result.exit_code == 0
    assert "No held-out accuracy snapshots recorded yet" in result.output


def test_eval_guard_history_json(tmp_path):
    history_path = tmp_path / "holdout_history.jsonl"
    append_jsonl(
        EvalSnapshot(
            timestamp="2026-07-01T00:00:00+00:00",
            corpus_size=10,
            corpus_sha="sha-a",
            accuracy=0.80,
            contig_version="0.38.0",
            detector="rules",
        ),
        history_path,
    )
    append_jsonl(
        EvalSnapshot(
            timestamp="2026-07-10T00:00:00+00:00",
            corpus_size=10,
            corpus_sha="sha-a",
            accuracy=0.90,
            contig_version="0.39.0",
            detector="rules",
        ),
        history_path,
    )

    result = runner.invoke(
        app,
        ["eval-guard", "--history", "--json", "--history-file", str(history_path)],
    )
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert isinstance(data, list)
    assert len(data) == 2


def test_eval_guard_bare_default_paths_unchanged():
    """Regression guard: a bare `eval-guard` (no new flags, default paths) must
    still print the exact pre-existing guard line and exit 0 -- proof --snapshot/
    --history/--history-file did not change guard behavior."""
    result = runner.invoke(app, ["eval-guard"])
    assert result.exit_code == 0
    assert "Guard PASS" in result.output
