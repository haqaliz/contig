"""Tests for `contig reproduce` (C8 slice 1, Phase 4): the user-facing CLI
command that ties load_claims/run_reproduction/write_reproduce_bundle together.

Mirrors tests/test_cli.py's conventions: no conftest, tmp_path, CliRunner, and a
fake executor injected via monkeypatch so no real process runs in CI.
"""

from __future__ import annotations

import json
import os

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


def _fake_executor(results=None, exit_code=0, output=""):
    """Mirrors _fake_run_executor in test_cli.py: writes a canned results.json
    into cwd (the repo dir, per run_reproduction's executor contract) and
    returns (exit_code, output). results=None means the script "did nothing"
    (exit_code should be nonzero in that case for a realistic fixture, but the
    caller controls both independently).
    """

    def execute(cmd, cwd):
        if results is not None:
            (cwd / "results.json").write_text(json.dumps(results))
        return exit_code, output

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


def test_reproduce_docstring_notes_table_locator_support():
    # S2: a one-line note that a claim locator may target a JSON path OR a
    # TSV/CSV cell. Assert on the raw docstring (what Click's `help` is built
    # from), not the Rich-rendered `--help` output -- see
    # test_reproduce_registers_allow_install_flag's comment on why CLI help
    # text assertions must introspect rather than scrape rendered output.
    from contig.cli import reproduce

    doc = reproduce.__doc__ or ""
    assert "tsv" in doc.lower() or "csv" in doc.lower()
    assert "row" in doc.lower() and "column" in doc.lower()


def test_reproduce_registers_allow_install_flag():
    # Assert the flag is a real registered option, not by scraping the Rich-
    # rendered `--help` text: with no TTY (as in CI) Rich wraps/reflows the long
    # `--allow-install/--no-allow-install` option and a substring check flakes.
    # Introspecting the Click command is deterministic across environments.
    import typer

    reproduce_cmd = typer.main.get_command(app).commands["reproduce"]
    opts = [o for p in reproduce_cmd.params for o in (list(p.opts) + list(p.secondary_opts))]
    assert "--allow-install" in opts
    assert "--no-allow-install" in opts


def test_reproduce_without_allow_install_flag_stays_unverified_on_failure(tmp_path, monkeypatch):
    # Default is off: a failing run with a detectable missing module still
    # yields all-unverified, and the installer seam is never touched.
    repo = _repo(tmp_path)
    claims = _claims_file(tmp_path, [{"id": "auc", "value": 0.9}])
    installer_calls = []
    monkeypatch.setattr(
        "contig.cli.default_command_executor",
        _fake_executor(results=None, exit_code=1, output="No module named 'numpy'"),
    )
    monkeypatch.setattr(
        "contig.cli.default_installer",
        lambda cmd, cwd: installer_calls.append((cmd, cwd)) or 0,
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
    assert installer_calls == []
    assert "env-repair" not in result.output


def test_reproduce_allow_install_heals_and_bundle_records_repair(tmp_path, monkeypatch):
    calls = {"n": 0}

    def execute(cmd, cwd):
        calls["n"] += 1
        if calls["n"] == 1:
            return 1, "ModuleNotFoundError: No module named 'numpy'"
        (cwd / "results.json").write_text(json.dumps({"auc": 0.9}))
        return 0, ""

    monkeypatch.setattr("contig.cli.default_command_executor", execute)
    monkeypatch.setattr("contig.cli.default_installer", lambda cmd, cwd: 0)

    repo = _repo(tmp_path)
    claims = _claims_file(tmp_path, [{"id": "auc", "value": 0.9}])
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
            "--allow-install",
        ],
    )
    assert result.exit_code == 0
    assert "REPRODUCED" in result.output.upper()
    assert "env-repair" in result.output
    assert "numpy" in result.output

    from contig.bundle import load_reproduction

    bundle_dir = next(p.parent for p in runs_dir.rglob("reproduce_record.json"))
    loaded = load_reproduction(bundle_dir)
    assert len(loaded.repair_history) == 1
    assert loaded.repair_history[0].outcome == "installed_and_retried"
    assert loaded.repair_history[0].patch.operation["install"] == "numpy"


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


# ---------------------------------------------------------------------------
# TSV/CSV table locator -- CLI containment + end-to-end [C8 slice 3, Phase 4]
# ---------------------------------------------------------------------------


def test_reproduce_escaping_table_locator_from_errors_and_writes_no_record(
    tmp_path, monkeypatch
):
    repo = _repo(tmp_path)
    claims = _claims_file(
        tmp_path,
        [
            {
                "id": "log2fc",
                "value": -2.31,
                "from": "../secret.tsv",
                "column": "log2FoldChange",
                "row": {"gene_id": "ENSG1"},
            }
        ],
    )
    monkeypatch.setattr("contig.cli.default_command_executor", _fake_executor({}))
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
    assert "../secret.tsv" in result.output
    assert not any(runs_dir.rglob("reproduce_record.json")) if runs_dir.exists() else True


def test_reproduce_absolute_table_locator_from_errors_and_writes_no_record(
    tmp_path, monkeypatch
):
    repo = _repo(tmp_path)
    claims = _claims_file(
        tmp_path,
        [
            {
                "id": "log2fc",
                "value": -2.31,
                "from": "/etc/de.tsv",
                "column": "log2FoldChange",
                "row": {"gene_id": "ENSG1"},
            }
        ],
    )
    monkeypatch.setattr("contig.cli.default_command_executor", _fake_executor({}))
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
    assert "/etc/de.tsv" in result.output
    assert not any(runs_dir.rglob("reproduce_record.json")) if runs_dir.exists() else True


_DE_HEADER = ["gene_id", "log2FoldChange", "padj"]


def _write_de_tsv_executor(observed: str):
    """Fake executor that emits a two-column-of-interest TSV under out/de.tsv,
    mirroring test_reproduce.py's run_reproduction table-locator fixtures.
    """

    def execute(cmd, cwd):
        out_dir = cwd / "out"
        out_dir.mkdir(parents=True, exist_ok=True)
        rows = [_DE_HEADER, ["ENSG1", observed, "0.001"]]
        (out_dir / "de.tsv").write_text("\n".join("\t".join(r) for r in rows) + "\n")
        return 0, ""

    return execute


def test_reproduce_located_table_claim_end_to_end_reports_verdict(tmp_path, monkeypatch):
    repo = _repo(tmp_path)
    claims = _claims_file(
        tmp_path,
        [
            {
                "id": "log2fc",
                "value": -2.31,
                "tolerance": 0.05,
                "from": "out/de.tsv",
                "column": "log2FoldChange",
                "row": {"gene_id": "ENSG1"},
            }
        ],
    )
    monkeypatch.setattr(
        "contig.cli.default_command_executor", _write_de_tsv_executor("-2.31")
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
    assert "REPRODUCED" in result.output.upper()
    assert "log2fc" in result.output
    assert any(runs_dir.rglob("reproduce_record.json"))


def test_reproduce_fail_on_diverged_exits_nonzero_for_table_claim(tmp_path, monkeypatch):
    repo = _repo(tmp_path)
    claims = _claims_file(
        tmp_path,
        [
            {
                "id": "log2fc",
                "value": -2.31,
                "tolerance": 0.05,
                "from": "out/de.tsv",
                "column": "log2FoldChange",
                "row": {"gene_id": "ENSG1"},
            }
        ],
    )
    monkeypatch.setattr(
        "contig.cli.default_command_executor", _write_de_tsv_executor("-1.0")
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
            "--fail-on-diverged",
        ],
    )
    assert result.exit_code != 0
    assert "DIVERGED" in result.output.upper()
    assert any(runs_dir.rglob("reproduce_record.json"))


# ---------------------------------------------------------------------------
# stdout/log pattern locator -- CLI containment + end-to-end [C8 slice 4, Phase 4]
# ---------------------------------------------------------------------------


def test_reproduce_stdout_pattern_claim_end_to_end_reports_verdict(tmp_path, monkeypatch):
    # M8/R5: a `from`-less pattern claim has locator.source is None. The pre-run
    # containment loop must SKIP it (there is no file to contain) rather than
    # joining repo_path / None -- which raises TypeError before any run.
    repo = _repo(tmp_path)
    claims = _claims_file(
        tmp_path,
        [
            {
                "id": "auc",
                "value": 0.91,
                "tolerance": 0.02,
                "pattern": "Final AUC: ([0-9.]+)",
            }
        ],
    )
    monkeypatch.setattr(
        "contig.cli.default_command_executor",
        _fake_executor(results=None, exit_code=0, output="Final AUC: 0.91\n"),
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
    assert "REPRODUCED" in result.output.upper()
    assert "auc" in result.output
    assert any(runs_dir.rglob("reproduce_record.json"))


def _write_train_log_executor(line: str):
    """Fake executor that emits a log file under logs/train.log, so a file-mode
    pattern claim (`from` + `pattern`) has something to read.
    """

    def execute(cmd, cwd):
        log_dir = cwd / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        (log_dir / "train.log").write_text(f"epoch 1 done\n{line}\n")
        return 0, ""

    return execute


def test_reproduce_file_pattern_claim_end_to_end_reports_verdict(tmp_path, monkeypatch):
    repo = _repo(tmp_path)
    claims = _claims_file(
        tmp_path,
        [
            {
                "id": "auc",
                "value": 0.91,
                "tolerance": 0.02,
                "from": "logs/train.log",
                "pattern": "Final AUC: ([0-9.]+)",
            }
        ],
    )
    monkeypatch.setattr(
        "contig.cli.default_command_executor",
        _write_train_log_executor("Final AUC: 0.91"),
    )
    runs_dir = tmp_path / "runs"
    result = runner.invoke(
        app,
        [
            "reproduce",
            str(repo),
            "--run",
            "python train.py",
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


def test_reproduce_escaping_pattern_locator_from_errors_and_writes_no_record(
    tmp_path, monkeypatch
):
    # A FILE-mode pattern claim keeps the existing pre-run refusal: its 'from'
    # is repo-relative like every other locator's.
    repo = _repo(tmp_path)
    claims = _claims_file(
        tmp_path,
        [
            {
                "id": "auc",
                "value": 0.91,
                "from": "../secret.log",
                "pattern": "Final AUC: ([0-9.]+)",
            }
        ],
    )
    monkeypatch.setattr("contig.cli.default_command_executor", _fake_executor({}))
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
    assert "../secret.log" in result.output
    assert not any(runs_dir.rglob("reproduce_record.json")) if runs_dir.exists() else True


def test_reproduce_absolute_pattern_locator_from_errors_and_writes_no_record(
    tmp_path, monkeypatch
):
    repo = _repo(tmp_path)
    claims = _claims_file(
        tmp_path,
        [
            {
                "id": "auc",
                "value": 0.91,
                "from": "/etc/passwd",
                "pattern": "root:x:([0-9]+)",
            }
        ],
    )
    monkeypatch.setattr("contig.cli.default_command_executor", _fake_executor({}))
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
    assert "/etc/passwd" in result.output
    assert not any(runs_dir.rglob("reproduce_record.json")) if runs_dir.exists() else True


def test_reproduce_uncompilable_pattern_errors_and_writes_no_record(tmp_path, monkeypatch):
    # G5 (CLI half): load_claims raises ClaimsError pre-run, so nothing runs and
    # no record is written.
    repo = _repo(tmp_path)
    claims = _claims_file(
        tmp_path,
        [{"id": "auc", "value": 0.91, "pattern": "([0-9"}],
    )
    monkeypatch.setattr("contig.cli.default_command_executor", _fake_executor({}))
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
    assert "auc" in result.output
    assert not any(runs_dir.rglob("reproduce_record.json")) if runs_dir.exists() else True


def test_reproduce_fail_on_diverged_exits_nonzero_for_pattern_claim(tmp_path, monkeypatch):
    repo = _repo(tmp_path)
    claims = _claims_file(
        tmp_path,
        [
            {
                "id": "auc",
                "value": 0.91,
                "tolerance": 0.02,
                "pattern": "Final AUC: ([0-9.]+)",
            }
        ],
    )
    monkeypatch.setattr(
        "contig.cli.default_command_executor",
        _fake_executor(results=None, exit_code=0, output="Final AUC: 0.42\n"),
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
            "--fail-on-diverged",
        ],
    )
    assert result.exit_code != 0
    assert "DIVERGED" in result.output.upper()
    assert any(runs_dir.rglob("reproduce_record.json"))


# ---------------------------------------------------------------------------
# notebook cell-output locator -- CLI containment + end-to-end [C8 slice 5, Phase 4]
# ---------------------------------------------------------------------------


def _notebook_doc(printed: str):
    """A minimal nbformat-4-ish notebook whose single code cell (index 0) has a
    stdout stream output printing `printed`.
    """
    return {
        "cells": [
            {
                "cell_type": "code",
                "source": ["print(auc)\n"],
                "outputs": [
                    {"output_type": "stream", "name": "stdout", "text": [printed]}
                ],
            }
        ],
        "metadata": {},
        "nbformat": 4,
        "nbformat_minor": 5,
    }


def _write_notebook_executor(printed: str, name: str = "out.ipynb"):
    """Fake executor that WRITES a fresh notebook into the repo dir during the
    run. Because it runs inside run_reproduction (after run_started_at is
    captured), the file's mtime is naturally >= run_started_at -- i.e. fresh.
    """

    def execute(cmd, cwd):
        (cwd / name).write_text(json.dumps(_notebook_doc(printed)))
        return 0, ""

    return execute


def test_reproduce_notebook_locator_fresh_end_to_end_reproduced(tmp_path, monkeypatch):
    # FRESH: the run rewrites out.ipynb, whose stdout cell prints the claimed
    # number -> the mtime is >= run_started_at, so the notebook resolves and the
    # claim reproduces.
    repo = _repo(tmp_path)
    claims = _claims_file(
        tmp_path,
        [
            {
                "id": "auc",
                "value": 0.91,
                "tolerance": 0.02,
                "from": "out.ipynb",
                "cell": 0,
                "pattern": "([0-9.]+)",
            }
        ],
    )
    monkeypatch.setattr(
        "contig.cli.default_command_executor", _write_notebook_executor("0.91")
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
    assert "REPRODUCED" in result.output.upper()
    assert "auc" in result.output
    assert any(runs_dir.rglob("reproduce_record.json"))


def test_reproduce_notebook_locator_stale_stays_unverified(tmp_path, monkeypatch):
    # STALE: out.ipynb is pre-created with an OLD mtime and the run does NOT
    # rewrite it. Even though the content matches the claim exactly, the mtime
    # predates run start, so the notebook is treated as not produced by this run
    # -> UNVERIFIED. Exit 0 (no --fail-on-diverged).
    repo = _repo(tmp_path)
    nb = repo / "out.ipynb"
    nb.write_text(json.dumps(_notebook_doc("0.91")))
    old = 1_000_000.0  # well before any run_started_at captured by the CLI
    os.utime(nb, (old, old))
    claims = _claims_file(
        tmp_path,
        [
            {
                "id": "auc",
                "value": 0.91,
                "tolerance": 0.02,
                "from": "out.ipynb",
                "cell": 0,
                "pattern": "([0-9.]+)",
            }
        ],
    )
    # Executor deliberately does NOT touch out.ipynb.
    monkeypatch.setattr(
        "contig.cli.default_command_executor",
        _fake_executor(results=None, exit_code=0, output=""),
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
    assert "UNVERIFIED" in result.output.upper()
    # The one claim is UNVERIFIED, not reproduced: the summary shows 0 reproduced.
    assert "0/1 REPRODUCED" in result.output.upper()
    assert "1 UNVERIFIED" in result.output.upper()
    assert any(runs_dir.rglob("reproduce_record.json"))


def test_reproduce_notebook_locator_missing_pattern_errors_and_writes_no_record(
    tmp_path, monkeypatch
):
    # MALFORMED: a notebook claim (has `cell`) missing `pattern` is rejected by
    # load_claims pre-run -> exit 1, nothing written, mirroring the other
    # malformed-claims tests.
    repo = _repo(tmp_path)
    claims = _claims_file(
        tmp_path,
        [{"id": "auc", "value": 0.91, "from": "out.ipynb", "cell": 0}],
    )
    monkeypatch.setattr("contig.cli.default_command_executor", _fake_executor({}))
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


def test_reproduce_escaping_notebook_locator_from_errors_and_writes_no_record(
    tmp_path, monkeypatch
):
    # ESCAPING: a notebook claim whose `from` escapes the repo is refused pre-run
    # by the containment loop (NotebookLocator.source is a real string, never
    # None, so the source-is-None skip does not apply) -> exit 1, no bundle.
    repo = _repo(tmp_path)
    claims = _claims_file(
        tmp_path,
        [
            {
                "id": "auc",
                "value": 0.91,
                "from": "../secret.ipynb",
                "cell": 0,
                "pattern": "([0-9.]+)",
            }
        ],
    )
    monkeypatch.setattr("contig.cli.default_command_executor", _fake_executor({}))
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
    assert "../secret.ipynb" in result.output
    assert not any(runs_dir.rglob("reproduce_record.json")) if runs_dir.exists() else True


def test_reproduce_docstring_notes_notebook_locator_support():
    # S2: the locator sentence must also document the notebook form. Assert on
    # the raw docstring, never the Rich-rendered `--help`.
    from contig.cli import reproduce

    doc = (reproduce.__doc__ or "").lower()
    assert "notebook" in doc
    assert "cell" in doc
    assert "mtime" in doc
    assert "unverified" in doc


def test_reproduce_docstring_notes_pattern_locator_support():
    # S2: the locator sentence must also document the pattern form. Assert on
    # the raw docstring (what Click's `help` is built from), never on the
    # Rich-rendered `--help` output -- see
    # test_reproduce_registers_allow_install_flag's comment on why.
    from contig.cli import reproduce

    doc = (reproduce.__doc__ or "").lower()
    assert "pattern" in doc
    assert "stdout" in doc
    assert "group 1" in doc
    assert "unverified" in doc
