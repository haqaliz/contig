"""Phase 1 (C7 live-cache enablement): sarek variant runs wire the annotation cache.

A real nf-core/sarek 3.5.1 run hard-fails at annotation-cache initialisation
unless a VEP/SnpEff cache resolves: with the default `s3://annotation-cache/…`
on a machine without AWS access, `annotation_cache_initialisation` `error()`s
before any verification fires. This slice wires the download at dispatch:
variant assays (VARIANT_ASSAYS) get `download_cache=true` and a deterministic
`outdir_cache` outside the run dir, so the shipped annotation verifiers finally
see an annotated VCF on real data.

Scope (honest): this proves the params are assembled into the dispatched argv
and the pre-flight refuses a bad cache dir — NOT that a real sarek run
completes (no real nf-core in CI; a real-run smoke test stays a manual
post-merge gate).
"""

import json
from pathlib import Path

from typer.testing import CliRunner

from contig.cli import _enable_annotation_cache, app
from contig.models import RunRecord
from contig.runner import build_nextflow_command

runner = CliRunner()

TRACE_RUN_OK = (
    "task_id\thash\tnative_id\tname\tstatus\texit\tsubmit\tduration\trealtime\n"
    "1\tab/cd\t1\tSTAR (S1)\tCOMPLETED\t0\t-\t-\t-\n"
)


def _self_heal_params_spy(captured):
    """Stand-in for self_heal_run that records the params dict it was handed and
    returns a minimal valid RunRecord so the CLI can render its report."""

    def spy(**kwargs):
        captured.append(kwargs.get("params"))
        return RunRecord(
            run_id=kwargs["run_id"],
            pipeline=kwargs["pipeline"],
            pipeline_revision=kwargs["revision"],
            target=kwargs["target"],
            input_checksums={},
        )

    return spy


# (a) a germline sarek run enables the annotation cache ---------------------------


def test_germline_run_enables_download_cache(tmp_path, monkeypatch):
    captured: list = []
    monkeypatch.setattr("contig.cli.self_heal_run", _self_heal_params_spy(captured))
    result = runner.invoke(
        app,
        ["run", "--run-id", "g", "--runs-dir", str(tmp_path),
         "--pipeline", "nf-core/sarek", "--revision", "3.5.1"],
    )
    assert result.exit_code == 0, result.output
    assert captured and captured[0] is not None
    assert captured[0].get("download_cache") == "true"
    expected_cache = str(
        (Path(tmp_path) / "caches" / "annotation" / "nf-core/sarek@3.5.1").resolve()
    )
    assert captured[0].get("outdir_cache") == expected_cache
    assert Path(expected_cache).is_dir()


# (b) the somatic entry enables it too --------------------------------------------


def test_somatic_run_enables_download_cache(tmp_path, monkeypatch):
    captured: list = []
    monkeypatch.setattr("contig.cli.self_heal_run", _self_heal_params_spy(captured))
    result = runner.invoke(
        app,
        ["run", "--run-id", "s", "--runs-dir", str(tmp_path),
         "--pipeline", "nf-core/sarek", "--revision", "3.5.1",
         "--assay", "somatic_variant_calling"],
    )
    assert result.exit_code == 0, result.output
    assert captured and captured[0] is not None
    assert captured[0].get("download_cache") == "true"
    expected_cache = str(
        (Path(tmp_path) / "caches" / "annotation" / "nf-core/sarek@3.5.1").resolve()
    )
    assert captured[0].get("outdir_cache") == expected_cache
    assert Path(expected_cache).is_dir()


# (c) RNA-seq stays untouched (no annotation tools, no dead params) ---------------


def test_rnaseq_run_no_cache_params(tmp_path, monkeypatch):
    captured: list = []
    monkeypatch.setattr("contig.cli.self_heal_run", _self_heal_params_spy(captured))
    result = runner.invoke(
        app,
        ["run", "--run-id", "r", "--runs-dir", str(tmp_path),
         "--pipeline", "nf-core/rnaseq"],
    )
    assert result.exit_code == 0, result.output
    assert captured and captured[0] is not None
    assert "download_cache" not in captured[0]
    assert "outdir_cache" not in captured[0]
    assert not (Path(tmp_path) / "caches").exists()


# (d) rerun/resume re-inject the same deterministic params via the persisted assay


def test_rerun_reinjects_cache_params_via_persisted_assay(tmp_path, monkeypatch):
    """launch.json persists the somatic assay; a rerun re-enters dispatch and
    re-wires the same annotation-cache params, so reproduce is faithful."""
    captured: list = []
    monkeypatch.setattr("contig.cli.self_heal_run", _self_heal_params_spy(captured))
    runs_dir = tmp_path / "runs"
    runner.invoke(
        app,
        ["run", "--run-id", "orig", "--runs-dir", str(runs_dir),
         "--pipeline", "nf-core/sarek", "--revision", "3.5.1",
         "--assay", "somatic_variant_calling"],
    )
    # the persisted assay is what carries the cache wiring across reproduce
    manifest = json.loads((runs_dir / "orig" / "launch.json").read_text())
    assert manifest["assay"] == "somatic_variant_calling"

    result = runner.invoke(
        app,
        ["rerun", "orig", "--runs-dir", str(runs_dir), "--new-run-id", "copy"],
    )
    assert result.exit_code == 0, result.output
    # both the original run and the replay assembled the same cache params
    assert len(captured) == 2
    assert captured[0].get("download_cache") == "true"
    assert captured[1].get("download_cache") == "true"
    assert captured[0].get("outdir_cache") == captured[1].get("outdir_cache")


# (e) user-supplied cache params win (setdefault semantics) -----------------------


def test_user_supplied_cache_params_win(tmp_path):
    params = {"download_cache": "false", "outdir_cache": "/custom"}
    _enable_annotation_cache(
        params,
        assay="variant_calling",
        pipeline="nf-core/sarek",
        revision="3.5.1",
        runs_dir=str(tmp_path),
        engine="nextflow",
    )
    assert params["download_cache"] == "false"
    assert params["outdir_cache"] == "/custom"


# (f) an uncreatable cache dir refuses before launch ------------------------------


def test_uncreatable_cache_dir_refuses_before_launch(tmp_path, monkeypatch):
    captured: list = []
    monkeypatch.setattr("contig.cli.self_heal_run", _self_heal_params_spy(captured))
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    (runs_dir / "caches").write_text("x")
    result = runner.invoke(
        app,
        ["run", "--run-id", "g", "--runs-dir", str(runs_dir),
         "--pipeline", "nf-core/sarek", "--revision", "3.5.1"],
    )
    assert result.exit_code == 1
    assert "Annotation cache dir" in result.output
    assert len(captured) == 0


# (g) the cache params become exact argv token pairs ------------------------------


def test_cache_argv_tokens():
    params = {"outdir": "/out", "download_cache": "true", "outdir_cache": "/cache/x"}
    cmd = build_nextflow_command(
        "nf-core/sarek", "3.5.1", ["docker"], "/trace", params=params
    )
    assert "--download_cache" in cmd
    assert cmd[cmd.index("--download_cache") + 1] == "true"
    assert "--outdir_cache" in cmd
    assert cmd[cmd.index("--outdir_cache") + 1] == "/cache/x"


# (h) the cache dir is absolute (sarek's directory-path format) -------------------


def test_cache_dir_absolute(tmp_path, monkeypatch):
    captured: list = []
    monkeypatch.setattr("contig.cli.self_heal_run", _self_heal_params_spy(captured))
    result = runner.invoke(
        app,
        ["run", "--run-id", "g", "--runs-dir", str(tmp_path),
         "--pipeline", "nf-core/sarek", "--revision", "3.5.1"],
    )
    assert result.exit_code == 0, result.output
    assert captured and captured[0] is not None
    assert captured[0]["outdir_cache"].startswith("/")
