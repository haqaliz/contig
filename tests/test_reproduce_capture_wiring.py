"""Wiring tests for reproduce-case capture (C8 slice 2, Task 3A): the
`contig reproduce` command appends a pending ReproduceCase sidecar after the
bundle write -- gated by should_capture_reproduce, always-on, never touching
the bundle itself.

Follows the scripted-executor pattern from test_cli_reproduce.py: the real
run_reproduction loop runs with a fake `contig.cli.default_command_executor`
that writes a canned results.json and returns a canned (exit_code, output).
"""

from __future__ import annotations

import json
import os
import time

from typer.testing import CliRunner

from contig.cli import app
from contig.reproduce_corpus import append_reproduce_case, load_reproduce_cases

runner = CliRunner()

RUN_ID = "run-capture-1"


def _repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    return repo


def _claims_file(tmp_path, claims):
    path = tmp_path / "claims.json"
    path.write_text(json.dumps(claims))
    return path


def _stamp_fresh(path):
    """Future-stamp an artifact the run binds, so the freshness guard
    (mtime >= run start) cannot flake on a coarse-mtime filesystem: the CLI
    stamps the run start sub-second (cli.py), and a filesystem that truncates
    mtime to the second can report the write as marginally before the stamp --
    the documented false-UNVERIFIED hazard. The guard's own deterministic
    fixtures use fixed os.utime stamps (reproduce_guard.py)."""

    now = time.time()
    os.utime(path, (now + 60, now + 60))


def _fake_executor(results=None, exit_code=0, output=""):
    def execute(cmd, cwd):
        if results is not None:
            path = cwd / "results.json"
            path.write_text(json.dumps(results))
            _stamp_fresh(path)
        return exit_code, output

    return execute


def _invoke(tmp_path, monkeypatch, executor):
    repo = _repo(tmp_path)
    claims = _claims_file(tmp_path, [{"id": "c1", "value": 42.0}])
    monkeypatch.setattr("contig.cli.default_command_executor", executor)
    monkeypatch.setattr("contig.cli._generate_run_id", lambda: RUN_ID)
    return runner.invoke(
        app,
        [
            "reproduce",
            str(repo),
            "--run",
            "python eval.py",
            "--claims",
            str(claims),
            "--runs-dir",
            str(tmp_path / "runs"),
        ],
    )


def _pending_path(tmp_path):
    return tmp_path / "runs" / "pending_reproduce_corpus.jsonl"


def _bundle_dir(tmp_path):
    return tmp_path / "runs" / RUN_ID


def test_diverged_run_appends_one_pending_case(tmp_path, monkeypatch):
    result = _invoke(tmp_path, monkeypatch, _fake_executor({"c1": 100.0}))
    assert result.exit_code == 0

    cases = load_reproduce_cases(_pending_path(tmp_path))
    assert len(cases) == 1
    case = cases[0]
    assert case.case_id == f"{RUN_ID}-reproduce"
    assert case.source == f"pending:{RUN_ID}"
    assert len(case.claims) == 1
    claim = case.claims[0]
    assert claim.claim_id == "c1"
    assert claim.claimed == 42.0
    assert claim.observed == 100.0
    assert claim.tolerance == 0.1
    assert claim.expected_status is None  # pre-classification inputs only

    # The bundle dir gains no files from capture: exactly the two the bundle
    # writer emits (no signature sidecar, no source checkout).
    assert sorted(p.name for p in _bundle_dir(tmp_path).iterdir()) == [
        "reproduce.json",
        "reproduce_record.json",
    ]


def test_clean_run_adds_no_pending_line(tmp_path, monkeypatch):
    pending_path = _pending_path(tmp_path)
    pending_path.parent.mkdir()
    pending_path.write_text('{"existing": true}\n')

    result = _invoke(tmp_path, monkeypatch, _fake_executor({"c1": 42.0}))
    assert result.exit_code == 0
    assert pending_path.read_text() == '{"existing": true}\n'


def test_unverified_run_is_captured(tmp_path, monkeypatch):
    result = _invoke(tmp_path, monkeypatch, _fake_executor(results=None, exit_code=1))
    assert result.exit_code == 0

    cases = load_reproduce_cases(_pending_path(tmp_path))
    assert len(cases) == 1
    assert cases[0].exit_code == 1
    assert cases[0].claims[0].observed is None


def test_capture_leaves_record_bytes_untouched(tmp_path, monkeypatch):
    record_bytes_at_capture = {}
    real_append = append_reproduce_case

    def spy(case, path):
        record_path = _bundle_dir(tmp_path) / "reproduce_record.json"
        record_bytes_at_capture["before"] = record_path.read_bytes()
        real_append(case, path)
        record_bytes_at_capture["after"] = record_path.read_bytes()

    monkeypatch.setattr("contig.cli.append_reproduce_case", spy)
    result = _invoke(tmp_path, monkeypatch, _fake_executor({"c1": 100.0}))
    assert result.exit_code == 0

    record_path = _bundle_dir(tmp_path) / "reproduce_record.json"
    assert record_bytes_at_capture["before"] == record_bytes_at_capture["after"]
    assert record_bytes_at_capture["before"] == record_path.read_bytes()
    # The sidecar still gained the case through the real append.
    assert len(load_reproduce_cases(_pending_path(tmp_path))) == 1
