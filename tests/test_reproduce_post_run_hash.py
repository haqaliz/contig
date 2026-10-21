"""C8-17: `ReproduceRecord.source_tree_sha256_post_run` -- the state of the
checkout AFTER the run, for remote runs only.

Strict TDD: written before the field exists. The pre-run
`source_tree_sha256` is untouched; the post-run digest reuses
`compute_tree_sha256` and is taken after `run_reproduction` returns. A local
run records `None` (there is no Contig-owned `source/` copy).

Part of the deliberate signature-break batch; old bundle JSON still loads.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from contig.bundle import compute_tree_sha256
from contig.cli import app
from contig.models import ReproduceRecord

runner = CliRunner()

_URL = "https://github.com/lab/paper-code"
_A_SHA = "a" * 40


class _ScriptedCheckoutFetcher:
    """Simulates `git clone` by materializing the checkout, then answers
    `git rev-parse HEAD` (the convention used by the other reproduce tests)."""

    def __init__(self, files=None, commit=_A_SHA):
        self.files = dict(files or {})
        self.commit = commit
        self.calls: list[tuple[list[str], Path]] = []

    def __call__(self, argv: list[str], cwd: Path) -> tuple[int, str]:
        self.calls.append((list(argv), Path(cwd)))
        if len(self.calls) == 1:
            dest = Path(argv[-1])
            for name, text in self.files.items():
                path = dest / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text)
            return 0, "Cloning into '...'\n"
        return 0, self.commit + "\n"


def _materialize(root: Path, files: dict[str, str]) -> Path:
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    return root


def _claims_file(tmp_path: Path) -> Path:
    path = tmp_path / "claims.json"
    path.write_text(json.dumps([{"id": "auc", "value": 0.9}]))
    return path


def _invoke(tmp_path: Path, claims: Path, runs_dir: Path, *, repo: str, extra=()):
    return runner.invoke(
        app,
        [
            "reproduce",
            repo,
            "--run",
            "python eval.py",
            "--claims",
            str(claims),
            "--runs-dir",
            str(runs_dir),
            *extra,
        ],
    )


def _bundle(runs_dir: Path) -> Path:
    (bundle,) = sorted(p for p in runs_dir.iterdir() if p.is_dir())
    return bundle


def _writing_executor(files: dict[str, str]):
    def executor(cmd, cwd):
        for name, text in files.items():
            (Path(cwd) / name).write_text(text)
        return 0, ""

    return executor


def test_post_run_hash_defaults_to_none_and_loads_old_json():
    record = ReproduceRecord(
        reproduce_id="rp_1",
        repo=".",
        run_command="python train.py",
        claims_sha256="a" * 64,
        claim_results=[],
        exit_code=0,
        created_at="2026-07-18T00:00:00Z",
    )
    assert record.source_tree_sha256_post_run is None

    legacy = {
        "reproduce_id": "rp_old",
        "repo": "https://github.com/example/paper",
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
    assert loaded.source_tree_sha256_post_run is None


def test_remote_run_records_post_run_tree_hash_and_keeps_pre_run_hash(tmp_path, monkeypatch):
    claims = _claims_file(tmp_path)
    runs_dir = tmp_path / "runs"
    fetch_files = {"code.py": "print('hi')\n"}
    fetcher = _ScriptedCheckoutFetcher(files=fetch_files)
    monkeypatch.setattr("contig.cli.default_fetcher", fetcher)
    # The run itself writes results.json into the checkout -- the post-run
    # hash must include it.
    monkeypatch.setattr(
        "contig.cli.default_command_executor",
        _writing_executor({"results.json": json.dumps({"auc": 0.9})}),
    )

    result = _invoke(tmp_path, claims, runs_dir, repo=_URL, extra=["--allow-fetch"])
    assert result.exit_code == 0, result.output

    record = json.loads((_bundle(runs_dir) / "reproduce_record.json").read_text())
    pre_run = compute_tree_sha256(_materialize(tmp_path / "expected_source", fetch_files))
    post_run = compute_tree_sha256(_bundle(runs_dir) / "source")

    assert record["source_tree_sha256"] == pre_run
    assert record["source_tree_sha256_post_run"] == post_run
    assert record["source_tree_sha256_post_run"] != record["source_tree_sha256"]


def test_local_run_leaves_post_run_tree_hash_none(tmp_path, monkeypatch):
    repo_dir = _materialize(tmp_path / "repo", {"code.py": "print('hi')\n"})
    claims = _claims_file(tmp_path)
    runs_dir = tmp_path / "runs"
    monkeypatch.setattr(
        "contig.cli.default_command_executor",
        _writing_executor({"results.json": json.dumps({"auc": 0.9})}),
    )

    result = _invoke(tmp_path, claims, runs_dir, repo=str(repo_dir))
    assert result.exit_code == 0, result.output

    record = json.loads((_bundle(runs_dir) / "reproduce_record.json").read_text())
    assert record["source_tree_sha256"] is not None
    assert record["source_tree_sha256_post_run"] is None
