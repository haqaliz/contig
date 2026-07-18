"""Tests for `contig reproduce` (C8 slice 1, Phase 4): the user-facing CLI
command that ties load_claims/run_reproduction/write_reproduce_bundle together.

Mirrors tests/test_cli.py's conventions: no conftest, tmp_path, CliRunner, and a
fake executor injected via monkeypatch so no real process runs in CI.
"""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from contig.cli import app

runner = CliRunner()


def _claims_file(tmp_path, claims):
    path = tmp_path / "claims.json"
    path.write_text(json.dumps(claims))
    return path


def _repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    return repo


def _fake_executor(results=None, exit_code=0):
    """Mirrors _fake_run_executor in test_cli.py: writes a canned results.json
    into cwd (the repo dir, per run_reproduction's executor contract) and
    returns (exit_code, ""). results=None means the script "did nothing"
    (exit_code should be nonzero in that case for a realistic fixture, but the
    caller controls both independently).
    """

    def execute(cmd, cwd):
        if results is not None:
            (cwd / "results.json").write_text(json.dumps(results))
        return exit_code, ""

    return execute


def test_reproduce_concordant_repo_reports_all_reproduced(tmp_path, monkeypatch):
    repo = _repo(tmp_path)
    claims = _claims_file(tmp_path, [{"id": "auc", "value": 0.9}])
    monkeypatch.setattr(
        "contig.cli.default_command_executor", _fake_executor({"auc": 0.9})
    )
    result = runner.invoke(
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
    assert result.exit_code == 0
    assert "REPRODUCED" in result.output.upper()
    assert "auc" in result.output


def test_reproduce_diverged_claim_names_observed_and_stated(tmp_path, monkeypatch):
    repo = _repo(tmp_path)
    claims = _claims_file(tmp_path, [{"id": "auc", "value": 0.9, "tolerance": 0.05}])
    monkeypatch.setattr(
        "contig.cli.default_command_executor", _fake_executor({"auc": 0.5})
    )
    result = runner.invoke(
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
    # Default (no --fail-on-diverged): exit 0 regardless of claim outcomes.
    assert result.exit_code == 0
    assert "DIVERGED" in result.output.upper()
    assert "0.9" in result.output
    assert "0.5" in result.output


def test_reproduce_nonzero_script_exit_marks_all_claims_unverified(tmp_path, monkeypatch):
    repo = _repo(tmp_path)
    claims = _claims_file(tmp_path, [{"id": "auc", "value": 0.9}])
    monkeypatch.setattr(
        "contig.cli.default_command_executor", _fake_executor(results=None, exit_code=1)
    )
    result = runner.invoke(
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
    assert result.exit_code == 0
    assert "UNVERIFIED" in result.output.upper()


def test_reproduce_malformed_claims_file_errors_and_writes_no_record(tmp_path, monkeypatch):
    repo = _repo(tmp_path)
    claims = tmp_path / "claims.json"
    # Duplicate claim id -> ClaimsError.
    claims.write_text(json.dumps([{"id": "auc", "value": 0.9}, {"id": "auc", "value": 0.5}]))
    monkeypatch.setattr(
        "contig.cli.default_command_executor", _fake_executor({"auc": 0.9})
    )
    runs_dir = tmp_path / "runs"
    result = runner.invoke(
        app,
        [
            "reproduce",
            str(repo),
            "--run",
            "python eval.py",
            "--claims",
            str(claims),
            "--runs-dir",
            str(runs_dir),
        ],
    )
    assert result.exit_code != 0
    assert result.output  # stderr message present (CliRunner mixes stderr into output by default)
    # Nothing written under runs_dir: no reproduce_record.json anywhere.
    assert not any(runs_dir.rglob("reproduce_record.json")) if runs_dir.exists() else True


def test_reproduce_malformed_json_claims_file_errors(tmp_path, monkeypatch):
    repo = _repo(tmp_path)
    claims = tmp_path / "claims.json"
    claims.write_text("{not valid json")
    monkeypatch.setattr(
        "contig.cli.default_command_executor", _fake_executor({"auc": 0.9})
    )
    result = runner.invoke(
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
    assert result.exit_code != 0


def test_reproduce_missing_repo_dir_errors(tmp_path):
    claims = _claims_file(tmp_path, [{"id": "auc", "value": 0.9}])
    result = runner.invoke(
        app,
        [
            "reproduce",
            str(tmp_path / "does-not-exist"),
            "--run",
            "python eval.py",
            "--claims",
            str(claims),
            "--runs-dir",
            str(tmp_path / "runs"),
        ],
    )
    assert result.exit_code != 0


def test_reproduce_fail_on_diverged_exits_nonzero(tmp_path, monkeypatch):
    repo = _repo(tmp_path)
    claims = _claims_file(tmp_path, [{"id": "auc", "value": 0.9, "tolerance": 0.05}])
    monkeypatch.setattr(
        "contig.cli.default_command_executor", _fake_executor({"auc": 0.5})
    )
    result = runner.invoke(
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
            "--fail-on-diverged",
        ],
    )
    assert result.exit_code != 0


def test_reproduce_fail_on_diverged_without_flag_exits_zero(tmp_path, monkeypatch):
    repo = _repo(tmp_path)
    claims = _claims_file(tmp_path, [{"id": "auc", "value": 0.9, "tolerance": 0.05}])
    monkeypatch.setattr(
        "contig.cli.default_command_executor", _fake_executor({"auc": 0.5})
    )
    result = runner.invoke(
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
    assert result.exit_code == 0


def test_reproduce_malformed_run_command_errors_and_writes_no_record(tmp_path, monkeypatch):
    repo = _repo(tmp_path)
    claims = _claims_file(tmp_path, [{"id": "auc", "value": 0.9}])
    monkeypatch.setattr(
        "contig.cli.default_command_executor", _fake_executor({"auc": 0.9})
    )
    runs_dir = tmp_path / "runs"
    result = runner.invoke(
        app,
        [
            "reproduce",
            str(repo),
            "--run",
            "python x 'y",  # unbalanced quote -> shlex.split raises ValueError
            "--claims",
            str(claims),
            "--runs-dir",
            str(runs_dir),
        ],
    )
    assert result.exit_code != 0
    assert result.output
    assert not any(runs_dir.rglob("reproduce_record.json")) if runs_dir.exists() else True


def test_reproduce_empty_run_command_errors_and_writes_no_record(tmp_path, monkeypatch):
    repo = _repo(tmp_path)
    claims = _claims_file(tmp_path, [{"id": "auc", "value": 0.9}])
    monkeypatch.setattr(
        "contig.cli.default_command_executor", _fake_executor({"auc": 0.9})
    )
    runs_dir = tmp_path / "runs"
    result = runner.invoke(
        app,
        [
            "reproduce",
            str(repo),
            "--run",
            "",
            "--claims",
            str(claims),
            "--runs-dir",
            str(runs_dir),
        ],
    )
    assert result.exit_code != 0
    assert result.output
    assert not any(runs_dir.rglob("reproduce_record.json")) if runs_dir.exists() else True


def test_reproduce_absolute_results_path_errors_and_writes_no_record(tmp_path, monkeypatch):
    repo = _repo(tmp_path)
    claims = _claims_file(tmp_path, [{"id": "auc", "value": 0.9}])
    monkeypatch.setattr(
        "contig.cli.default_command_executor", _fake_executor({"auc": 0.9})
    )
    runs_dir = tmp_path / "runs"
    result = runner.invoke(
        app,
        [
            "reproduce",
            str(repo),
            "--run",
            "python eval.py",
            "--claims",
            str(claims),
            "--results",
            "/etc/passwd",
            "--runs-dir",
            str(runs_dir),
        ],
    )
    assert result.exit_code != 0
    assert result.output
    assert not any(runs_dir.rglob("reproduce_record.json")) if runs_dir.exists() else True


def test_reproduce_escaping_results_path_errors_and_writes_no_record(tmp_path, monkeypatch):
    repo = _repo(tmp_path)
    claims = _claims_file(tmp_path, [{"id": "auc", "value": 0.9}])
    monkeypatch.setattr(
        "contig.cli.default_command_executor", _fake_executor({"auc": 0.9})
    )
    runs_dir = tmp_path / "runs"
    result = runner.invoke(
        app,
        [
            "reproduce",
            str(repo),
            "--run",
            "python eval.py",
            "--claims",
            str(claims),
            "--results",
            "../secret.json",
            "--runs-dir",
            str(runs_dir),
        ],
    )
    assert result.exit_code != 0
    assert result.output
    assert not any(runs_dir.rglob("reproduce_record.json")) if runs_dir.exists() else True


def test_reproduce_escaping_locator_from_errors_and_writes_no_record(tmp_path, monkeypatch):
    repo = _repo(tmp_path)
    claims = _claims_file(
        tmp_path,
        [{"id": "auc", "value": 0.9, "from": "../secret.json", "path": "$.model.auc"}],
    )
    monkeypatch.setattr(
        "contig.cli.default_command_executor", _fake_executor({"auc": 0.9})
    )
    runs_dir = tmp_path / "runs"
    result = runner.invoke(
        app,
        [
            "reproduce",
            str(repo),
            "--run",
            "python eval.py",
            "--claims",
            str(claims),
            "--runs-dir",
            str(runs_dir),
        ],
    )
    assert result.exit_code != 0
    assert result.output
    assert not any(runs_dir.rglob("reproduce_record.json")) if runs_dir.exists() else True


def test_reproduce_absolute_locator_from_errors_and_writes_no_record(tmp_path, monkeypatch):
    repo = _repo(tmp_path)
    claims = _claims_file(
        tmp_path,
        [{"id": "auc", "value": 0.9, "from": "/etc/passwd", "path": "$.model.auc"}],
    )
    monkeypatch.setattr(
        "contig.cli.default_command_executor", _fake_executor({"auc": 0.9})
    )
    runs_dir = tmp_path / "runs"
    result = runner.invoke(
        app,
        [
            "reproduce",
            str(repo),
            "--run",
            "python eval.py",
            "--claims",
            str(claims),
            "--runs-dir",
            str(runs_dir),
        ],
    )
    assert result.exit_code != 0
    assert result.output
    assert not any(runs_dir.rglob("reproduce_record.json")) if runs_dir.exists() else True


def test_reproduce_located_claim_end_to_end_reports_verdict(tmp_path, monkeypatch):
    repo = _repo(tmp_path)
    claims = _claims_file(
        tmp_path,
        [{"id": "auc", "value": 0.9, "from": "out/summary.json", "path": "$.model.auc"}],
    )

    def execute(cmd, cwd):
        (cwd / "out").mkdir(parents=True, exist_ok=True)
        (cwd / "out" / "summary.json").write_text(json.dumps({"model": {"auc": 0.9}}))
        return 0, ""

    monkeypatch.setattr("contig.cli.default_command_executor", execute)
    runs_dir = tmp_path / "runs"
    result = runner.invoke(
        app,
        [
            "reproduce",
            str(repo),
            "--run",
            "python eval.py",
            "--claims",
            str(claims),
            "--runs-dir",
            str(runs_dir),
        ],
    )
    assert result.exit_code == 0
    assert "REPRODUCED" in result.output.upper()
    assert "auc" in result.output
    assert any(runs_dir.rglob("reproduce_record.json"))


def test_reproduce_writes_signed_bundle_when_signing_key_set(tmp_path, monkeypatch):
    from contig import signing

    if not signing.signing_available():
        pytest.skip("cryptography not installed")
    priv, _pub = signing.generate_keypair()
    monkeypatch.setenv("CONTIG_SIGNING_KEY", priv)
    repo = _repo(tmp_path)
    claims = _claims_file(tmp_path, [{"id": "auc", "value": 0.9}])
    monkeypatch.setattr(
        "contig.cli.default_command_executor", _fake_executor({"auc": 0.9})
    )
    runs_dir = tmp_path / "runs"
    result = runner.invoke(
        app,
        [
            "reproduce",
            str(repo),
            "--run",
            "python eval.py",
            "--claims",
            str(claims),
            "--runs-dir",
            str(runs_dir),
        ],
    )
    assert result.exit_code == 0
    signature_files = list(runs_dir.rglob("signature.json"))
    assert len(signature_files) == 1
