"""C8-16: opt-in pruning of old remote reproduce checkouts.

A `--allow-fetch` run clones into `<runs-dir>/<id>/source`, and nothing ever
removed those trees. `contig reproduce --prune-checkouts N` removes the
checkouts of the N oldest remote runs after a successful remote run. These
tests drive the real CLI with the fetcher/executor seams faked, plus one direct
test of the failure-reporting contract.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from typer.testing import CliRunner

from contig.cli import app

runner = CliRunner()

_URL = "https://github.com/lab/paper-code"
_SHA = "a" * 40


class _Fetcher:
    def __init__(self):
        self.calls = 0

    def __call__(self, argv, cwd):
        self.calls += 1
        return (0, _SHA + "\n")


def _claims_file(tmp_path):
    path = tmp_path / "claims.json"
    path.write_text(json.dumps([{"id": "auc", "value": 0.9}]))
    return path


def _remote_run(runs_dir: Path, run_id: str, created_at: str) -> Path:
    """A past remote run bundle: record says source_url, checkout on disk."""
    bundle = runs_dir / run_id
    (bundle / "source").mkdir(parents=True)
    (bundle / "source" / "paper.py").write_text("print(1)\n")
    (bundle / "reproduce_record.json").write_text(
        json.dumps(
            {
                "reproduce_id": run_id,
                "repo": _URL,
                "run_command": "python eval.py",
                "claims_sha256": "0" * 64,
                "claim_results": [],
                "exit_code": 0,
                "created_at": created_at,
                "source_url": _URL,
            }
        )
    )
    return bundle


def _invoke(tmp_path, runs_dir, *, extra=()):
    return runner.invoke(
        app,
        [
            "reproduce",
            _URL,
            "--run",
            "python eval.py",
            "--claims",
            str(_claims_file(tmp_path)),
            "--runs-dir",
            str(runs_dir),
            "--allow-fetch",
            *extra,
        ],
    )


def _patch_seams(monkeypatch, executor):
    fetcher = _Fetcher()
    monkeypatch.setattr("contig.cli.default_fetcher", fetcher)
    monkeypatch.setattr("contig.cli.default_command_executor", executor)
    return fetcher


def _ok_executor(cmd, cwd):
    (Path(cwd) / "results.json").write_text(json.dumps({"auc": 0.9}))
    return 0, ""


def _fail_executor(cmd, cwd):
    return 1, "boom"


def _current_bundle(runs_dir: Path, past: list[Path]) -> Path:
    (bundle,) = [p for p in runs_dir.iterdir() if p.is_dir() and p not in past]
    return bundle


def test_prune_removes_the_n_oldest_remote_checkouts_and_keeps_the_current(
    tmp_path, monkeypatch
):
    runs_dir = tmp_path / "runs"
    past = [
        _remote_run(runs_dir, f"run-2026-01-0{i}T00-00-00-000000Z", f"2026-01-0{i}T00:00:00+00:00")
        for i in (3, 1, 2)  # created out of directory order on purpose
    ]
    _patch_seams(monkeypatch, _ok_executor)

    result = _invoke(tmp_path, runs_dir, extra=["--prune-checkouts", "2"])

    assert result.exit_code == 0, result.output
    oldest, middle, newest = sorted(past, key=lambda p: p.name)
    assert not (oldest / "source").exists()
    assert not (middle / "source").exists()
    assert (newest / "source").is_dir()
    # The bundle itself is never removed -- only the checkout it owns.
    assert oldest.is_dir() and middle.is_dir()
    current = _current_bundle(runs_dir, past)
    assert (current / "source").is_dir()


def test_prune_never_touches_a_local_runs_directory(tmp_path, monkeypatch):
    runs_dir = tmp_path / "runs"
    local = runs_dir / "run-2020-01-01T00-00-00-000000Z"
    (local / "source").mkdir(parents=True)
    (local / "source" / "keep.txt").write_text("keep me")
    (local / "reproduce_record.json").write_text(
        json.dumps(
            {
                "reproduce_id": local.name,
                "repo": "/some/local/repo",
                "run_command": "python eval.py",
                "claims_sha256": "0" * 64,
                "claim_results": [],
                "exit_code": 0,
                "created_at": "2020-01-01T00:00:00+00:00",
                "source_url": None,
            }
        )
    )
    _patch_seams(monkeypatch, _ok_executor)

    result = _invoke(tmp_path, runs_dir, extra=["--prune-checkouts", "5"])

    assert result.exit_code == 0, result.output
    assert (local / "source" / "keep.txt").read_text() == "keep me"


def test_failed_run_prunes_nothing(tmp_path, monkeypatch):
    runs_dir = tmp_path / "runs"
    past = [_remote_run(runs_dir, "run-2026-01-01T00-00-00-000000Z", "2026-01-01T00:00:00+00:00")]
    _patch_seams(monkeypatch, _fail_executor)

    result = _invoke(tmp_path, runs_dir, extra=["--prune-checkouts", "1"])

    assert "run did not complete (exit 1)" in result.output
    assert (past[0] / "source").is_dir()


def test_non_positive_prune_count_is_refused_before_any_work(tmp_path, monkeypatch):
    for n in ("0", "-1"):
        runs_dir = tmp_path / f"runs-{n}"
        fetcher = _patch_seams(monkeypatch, _ok_executor)

        result = _invoke(tmp_path, runs_dir, extra=["--prune-checkouts", n])

        assert result.exit_code != 0, result.output
        assert "positive" in result.output.lower()
        assert fetcher.calls == 0
        assert not runs_dir.exists()


def test_failed_removal_is_reported_and_not_swallowed(tmp_path, monkeypatch):
    runs_dir = tmp_path / "runs"
    past = [_remote_run(runs_dir, "run-2026-01-01T00-00-00-000000Z", "2026-01-01T00:00:00+00:00")]
    _patch_seams(monkeypatch, _ok_executor)
    doomed = past[0] / "source"
    real_rmtree = shutil.rmtree

    def flaky_rmtree(path, *args, **kwargs):
        if Path(path) == doomed:
            raise OSError("permission denied")
        return real_rmtree(path, *args, **kwargs)

    monkeypatch.setattr("contig.verification.reproduce.shutil.rmtree", flaky_rmtree)

    result = _invoke(tmp_path, runs_dir, extra=["--prune-checkouts", "1"])

    assert result.exit_code == 0, result.output
    assert "permission denied" in result.output
    assert doomed.is_dir()
