"""C8-18: local `source_commit` / `source_dirty` capture.

Strict TDD: written before the field/helper exists. For a local repo path the
record pins the HEAD commit and whether the working tree was dirty when the
run started. Git is optional: a missing git binary or a non-repository path
degrades to `(None, None)` and never fails the run. Remote behaviour is
unchanged (`source_commit` stays the fetched SHA, `source_dirty` stays None).

Part of the deliberate signature-break batch; old bundle JSON still loads.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from contig.cli import _local_git_state, app
from contig.models import ReproduceRecord

runner = CliRunner()

requires_git = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def _git_repo(path: Path, files: dict[str, str] | None = None) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "-q")
    _git(path, "config", "user.email", "test@example.com")
    _git(path, "config", "user.name", "Test")
    for name, text in (files or {"code.py": "print('hi')\n"}).items():
        target = path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
    _git(path, "add", ".")
    _git(path, "commit", "-q", "-m", "init")
    return path


def test_source_dirty_defaults_to_none_and_loads_old_json():
    record = ReproduceRecord(
        reproduce_id="rp_1",
        repo=".",
        run_command="python train.py",
        claims_sha256="a" * 64,
        claim_results=[],
        exit_code=0,
        created_at="2026-07-18T00:00:00Z",
    )
    assert record.source_dirty is None

    legacy = {
        "reproduce_id": "rp_old",
        "repo": "./repo",
        "run_command": "python train.py",
        "claims_sha256": "a" * 64,
        "claim_results": [],
        "exit_code": 0,
        "created_at": "2026-07-18T00:00:00Z",
        "source_url": None,
        "source_commit": None,
        "source_tree_sha256": None,
    }
    loaded = ReproduceRecord.model_validate_json(json.dumps(legacy))
    assert loaded.source_commit is None
    assert loaded.source_dirty is None


@requires_git
def test_clean_git_repo_reports_head_and_not_dirty(tmp_path):
    repo = _git_repo(tmp_path / "repo")

    commit, dirty = _local_git_state(repo)

    assert commit == _git(repo, "rev-parse", "HEAD")
    assert dirty is False


@requires_git
def test_untracked_file_makes_the_repo_dirty(tmp_path):
    repo = _git_repo(tmp_path / "repo")
    (repo / "scratch.txt").write_text("uncommitted\n")

    commit, dirty = _local_git_state(repo)

    assert commit == _git(repo, "rev-parse", "HEAD")
    assert dirty is True


def test_non_git_directory_is_inert(tmp_path):
    plain = tmp_path / "plain"
    plain.mkdir()

    assert _local_git_state(plain) == (None, None)


def test_missing_git_binary_is_inert(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()

    def _no_git(*args, **kwargs):
        raise FileNotFoundError("git")

    monkeypatch.setattr("contig.cli.subprocess.run", _no_git)

    assert _local_git_state(repo) == (None, None)


@requires_git
def test_local_cli_run_records_commit_and_clean_state(tmp_path, monkeypatch):
    repo = _git_repo(tmp_path / "repo")
    expected_commit = _git(repo, "rev-parse", "HEAD")
    claims = tmp_path / "claims.json"
    claims.write_text(json.dumps([{"id": "auc", "value": 0.9}]))
    runs_dir = tmp_path / "runs"

    def executor(cmd, cwd):
        # Untracked output written BY the run: the captured dirty flag must
        # describe the pre-run state, not this.
        (Path(cwd) / "results.json").write_text(json.dumps({"auc": 0.9}))
        return 0, ""

    monkeypatch.setattr("contig.cli.default_command_executor", executor)

    result = runner.invoke(
        app,
        ["reproduce", str(repo), "--run", "python eval.py", "--claims", str(claims),
         "--runs-dir", str(runs_dir)],
    )
    assert result.exit_code == 0, result.output

    (bundle,) = [p for p in runs_dir.iterdir() if p.is_dir()]
    record = json.loads((bundle / "reproduce_record.json").read_text())
    assert record["source_commit"] == expected_commit
    assert record["source_dirty"] is False


@requires_git
def test_local_cli_run_records_a_dirty_working_tree(tmp_path, monkeypatch):
    repo = _git_repo(tmp_path / "repo")
    (repo / "uncommitted.py").write_text("x = 1\n")
    claims = tmp_path / "claims.json"
    claims.write_text(json.dumps([{"id": "auc", "value": 0.9}]))
    runs_dir = tmp_path / "runs"
    monkeypatch.setattr(
        "contig.cli.default_command_executor",
        lambda cmd, cwd: (
            (Path(cwd) / "results.json").write_text(json.dumps({"auc": 0.9})),
            (0, ""),
        )[1],
    )

    result = runner.invoke(
        app,
        ["reproduce", str(repo), "--run", "python eval.py", "--claims", str(claims),
         "--runs-dir", str(runs_dir)],
    )
    assert result.exit_code == 0, result.output

    (bundle,) = [p for p in runs_dir.iterdir() if p.is_dir()]
    record = json.loads((bundle / "reproduce_record.json").read_text())
    assert record["source_dirty"] is True


def test_remote_run_leaves_source_dirty_none(tmp_path, monkeypatch):
    claims = tmp_path / "claims.json"
    claims.write_text(json.dumps([{"id": "auc", "value": 0.9}]))
    runs_dir = tmp_path / "runs"

    class _Fetcher:
        def __init__(self):
            self.calls = 0

        def __call__(self, argv, cwd):
            self.calls += 1
            if self.calls == 1:
                dest = Path(argv[-1])
                dest.mkdir(parents=True, exist_ok=True)
                (dest / "code.py").write_text("print('hi')\n")
                return 0, ""
            return 0, "b" * 40 + "\n"

    monkeypatch.setattr("contig.cli.default_fetcher", _Fetcher())
    monkeypatch.setattr(
        "contig.cli.default_command_executor",
        lambda cmd, cwd: (
            (Path(cwd) / "results.json").write_text(json.dumps({"auc": 0.9})),
            (0, ""),
        )[1],
    )

    result = runner.invoke(
        app,
        ["reproduce", "https://github.com/lab/paper-code", "--run", "python eval.py",
         "--claims", str(claims), "--runs-dir", str(runs_dir), "--allow-fetch"],
    )
    assert result.exit_code == 0, result.output

    (bundle,) = [p for p in runs_dir.iterdir() if p.is_dir()]
    record = json.loads((bundle / "reproduce_record.json").read_text())
    assert record["source_commit"] == "b" * 40
    assert record["source_dirty"] is None
