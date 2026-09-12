"""C7 follow-on: user-supplied annotation cache inputs + explicit-reference guard.

The parent slice (annotation-cache-wiring) made sarek variant runs annotate at
all by injecting `download_cache=true` + a deterministic `outdir_cache`. This
slice adds the typed user-supplied `--vep-cache`/`--snpeff-cache` flags, the
explicit-reference guard (a custom `--fasta/--gtf` variant run with neither user
cache is refused before anything launches, because the auto-download is keyed to
sarek's default GRCh38), and manifest replay across rerun/resume.

Scope (honest): this proves the params are assembled, the refusal fires before
launch, and the flags survive reproduce — NOT that a real sarek run completes
(no real nf-core in CI; a real-run smoke test stays a manual post-merge gate).
"""

import json
from pathlib import Path

import pytest
import typer
from typer.testing import CliRunner

from contig.cli import _enable_annotation_cache, app
from contig.models import LaunchManifest, RunRecord
from contig.runner import build_nextflow_command
from contig.runner import build_nextflow_command

runner = CliRunner()


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


def _call_seam(params, *, assay="variant_calling", runs_dir, vep_cache=None, snpeff_cache=None):
    _enable_annotation_cache(
        params,
        assay=assay,
        pipeline="nf-core/sarek",
        revision="3.5.1",
        runs_dir=runs_dir,
        engine="nextflow",
        vep_cache=vep_cache,
        snpeff_cache=snpeff_cache,
    )


# Task 1 -- seam logic (M2/M3), params level ----------------------------------


def test_both_caches_via_kwargs_win_over_autodownload(tmp_path):
    params: dict[str, object] = {}
    _call_seam(params, runs_dir=str(tmp_path), vep_cache="/v", snpeff_cache="/s")
    assert params["vep_cache"] == "/v"
    assert params["snpeff_cache"] == "/s"
    assert "download_cache" not in params
    assert "outdir_cache" not in params
    assert not (Path(tmp_path) / "caches").exists()


def test_preset_opt_value_wins_over_flag_kwarg(tmp_path):
    params: dict[str, object] = {"vep_cache": "/optv"}
    _call_seam(params, runs_dir=str(tmp_path), vep_cache="/flagv", snpeff_cache="/s")
    assert params["vep_cache"] == "/optv"
    assert params["snpeff_cache"] == "/s"
    assert "download_cache" not in params
    assert "outdir_cache" not in params


def test_explicit_mode_no_caches_refuses_before_mkdir(tmp_path, capsys):
    params: dict[str, object] = {"fasta": "/ref.fa", "gtf": "/ref.gtf"}
    with pytest.raises(typer.Exit) as exc:
        _call_seam(params, runs_dir=str(tmp_path))
    assert exc.value.exit_code == 1
    err = capsys.readouterr().err
    assert "--vep-cache" in err
    assert "--snpeff-cache" in err
    assert params == {"fasta": "/ref.fa", "gtf": "/ref.gtf"}  # no mutation
    assert not (Path(tmp_path) / "caches").exists()


def test_explicit_mode_single_cache_refuses(tmp_path, capsys):
    params: dict[str, object] = {"fasta": "/ref.fa", "gtf": "/ref.gtf"}
    with pytest.raises(typer.Exit) as exc:
        _call_seam(params, runs_dir=str(tmp_path), vep_cache="/v")
    assert exc.value.exit_code == 1
    err = capsys.readouterr().err
    assert "--vep-cache" in err
    assert "--snpeff-cache" in err
    assert not (Path(tmp_path) / "caches").exists()


def test_explicit_mode_both_caches_proceeds(tmp_path):
    params: dict[str, object] = {"fasta": "/ref.fa", "gtf": "/ref.gtf"}
    _call_seam(params, runs_dir=str(tmp_path), vep_cache="/v", snpeff_cache="/s")
    assert params["vep_cache"] == "/v"
    assert params["snpeff_cache"] == "/s"
    assert "download_cache" not in params
    assert "outdir_cache" not in params
    assert not (Path(tmp_path) / "caches").exists()


def test_igenomes_mode_no_caches_injects_download(tmp_path):
    params: dict[str, object] = {"genome": "GRCh38"}
    _call_seam(params, runs_dir=str(tmp_path))
    assert params["download_cache"] == "true"
    assert params["outdir_cache"] == str(
        (Path(tmp_path) / "caches" / "annotation" / "nf-core/sarek@3.5.1").resolve()
    )
    assert (Path(tmp_path) / "caches").exists()


def test_igenomes_mode_both_caches_no_download_params(tmp_path):
    params: dict[str, object] = {"genome": "GRCh38"}
    _call_seam(params, runs_dir=str(tmp_path), vep_cache="/v", snpeff_cache="/s")
    assert params["vep_cache"] == "/v"
    assert params["snpeff_cache"] == "/s"
    assert "download_cache" not in params
    assert "outdir_cache" not in params


def test_igenomes_single_vep_cache_keeps_download_for_missing_tool(tmp_path):
    params: dict[str, object] = {"genome": "GRCh38"}
    _call_seam(params, runs_dir=str(tmp_path), vep_cache="/v")
    assert params["vep_cache"] == "/v"
    assert params["download_cache"] == "true"
    assert params["outdir_cache"] == str(
        (Path(tmp_path) / "caches" / "annotation" / "nf-core/sarek@3.5.1").resolve()
    )


def test_non_variant_assay_ignores_cache_kwargs(tmp_path):
    params: dict[str, object] = {"genome": "GRCh38"}
    _call_seam(params, assay="rnaseq", runs_dir=str(tmp_path), vep_cache="/v", snpeff_cache="/s")
    assert params == {"genome": "GRCh38"}


# Task 2 -- CLI flags threaded through dispatch (M1), typer level --------------


def test_run_with_both_flags_passes_caches_and_no_download(tmp_path, monkeypatch):
    captured: list = []
    monkeypatch.setattr("contig.cli.self_heal_run", _self_heal_params_spy(captured))
    result = runner.invoke(
        app,
        ["run", "--run-id", "cf", "--runs-dir", str(tmp_path),
         "--pipeline", "nf-core/sarek", "--revision", "3.5.1",
         "--vep-cache", "/v", "--snpeff-cache", "/s"],
    )
    assert result.exit_code == 0, result.output
    assert captured and captured[0] is not None
    assert captured[0].get("vep_cache") == "/v"
    assert captured[0].get("snpeff_cache") == "/s"
    assert "download_cache" not in captured[0]
    assert "outdir_cache" not in captured[0]
    assert not (Path(tmp_path) / "caches").exists()


def _make_sheet(tmp_path):
    (tmp_path / "s1_R1.fastq.gz").write_bytes(b"\x1f\x8bR1")
    (tmp_path / "s1_R2.fastq.gz").write_bytes(b"\x1f\x8bR2")
    sheet = tmp_path / "samplesheet.csv"
    sheet.write_text(f"sample,fastq_1,fastq_2,strandedness\nS1,s1_R1.fastq.gz,s1_R2.fastq.gz,auto\n")
    return sheet


def _make_overlapping_reference(tmp_path):
    fasta = tmp_path / "ref.fa"
    fasta.write_text(">chr1\nACGT\n>chr2\nTTTT\n")
    gtf = tmp_path / "ref.gtf"
    gtf.write_text("chr1\tsource\tgene\t1\t100\t.\t+\t.\tgene_id \"g1\"\n")
    return fasta, gtf


def test_explicit_reference_no_caches_refuses_before_launch(tmp_path, monkeypatch):
    sheet = _make_sheet(tmp_path)
    fasta, gtf = _make_overlapping_reference(tmp_path)
    captured: list = []
    monkeypatch.setattr("contig.cli.self_heal_run", _self_heal_params_spy(captured))
    result = runner.invoke(
        app,
        ["run", "--run-id", "exref", "--runs-dir", str(tmp_path / "runs"),
         "--pipeline", "nf-core/sarek", "--revision", "3.5.1",
         "--input", str(sheet), "--fasta", str(fasta), "--gtf", str(gtf)],
    )
    assert result.exit_code == 1
    assert "--vep-cache" in result.output
    assert "--snpeff-cache" in result.output
    assert len(captured) == 0  # nothing launched
    assert not (tmp_path / "runs" / "caches").exists()


def test_explicit_reference_both_caches_proceeds(tmp_path, monkeypatch):
    sheet = _make_sheet(tmp_path)
    fasta, gtf = _make_overlapping_reference(tmp_path)
    captured: list = []
    monkeypatch.setattr("contig.cli.self_heal_run", _self_heal_params_spy(captured))
    result = runner.invoke(
        app,
        ["run", "--run-id", "exrefok", "--runs-dir", str(tmp_path / "runs"),
         "--pipeline", "nf-core/sarek", "--revision", "3.5.1",
         "--input", str(sheet), "--fasta", str(fasta), "--gtf", str(gtf),
         "--vep-cache", "/v", "--snpeff-cache", "/s"],
    )
    assert result.exit_code == 0, result.output
    assert captured and captured[0] is not None
    assert captured[0].get("vep_cache") == "/v"
    assert captured[0].get("snpeff_cache") == "/s"
    assert "download_cache" not in captured[0]
    assert "outdir_cache" not in captured[0]


# Task 3 -- manifest replay (M4): fields + rerun/resume -----------------------


def test_launch_manifest_roundtrips_cache_inputs():
    manifest = LaunchManifest(
        run_id="r1", pipeline="nf-core/sarek", revision="3.5.1",
        profiles=["docker"], backend="local", container_runtime="docker",
        vep_cache="/v", snpeff_cache="/s", created_at="2026-09-12T00:00:00Z",
    )
    restored = LaunchManifest.model_validate_json(manifest.model_dump_json())
    assert restored.vep_cache == "/v"
    assert restored.snpeff_cache == "/s"


def test_launch_manifest_cache_inputs_default_none():
    legacy = LaunchManifest(
        run_id="r1", pipeline="nf-core/sarek", revision="3.5.1",
        profiles=["docker"], backend="local", container_runtime="docker",
        created_at="2026-09-12T00:00:00Z",
    )
    assert legacy.vep_cache is None
    assert legacy.snpeff_cache is None


def test_run_manifest_persists_cache_inputs(tmp_path, monkeypatch):
    captured: list = []
    monkeypatch.setattr("contig.cli.self_heal_run", _self_heal_params_spy(captured))
    result = runner.invoke(
        app,
        ["run", "--run-id", "cfm", "--runs-dir", str(tmp_path),
         "--pipeline", "nf-core/sarek", "--revision", "3.5.1",
         "--vep-cache", "/v", "--snpeff-cache", "/s"],
    )
    assert result.exit_code == 0, result.output
    manifest = json.loads((Path(tmp_path) / "cfm" / "launch.json").read_text())
    assert manifest["vep_cache"] == "/v"
    assert manifest["snpeff_cache"] == "/s"


def test_rerun_replays_cache_inputs(tmp_path, monkeypatch):
    captured: list = []
    monkeypatch.setattr("contig.cli.self_heal_run", _self_heal_params_spy(captured))
    runs_dir = tmp_path / "runs"
    result = runner.invoke(
        app,
        ["run", "--run-id", "cfrr", "--runs-dir", str(runs_dir),
         "--pipeline", "nf-core/sarek", "--revision", "3.5.1",
         "--vep-cache", "/v", "--snpeff-cache", "/s"],
    )
    assert result.exit_code == 0, result.output
    result = runner.invoke(
        app,
        ["rerun", "cfrr", "--runs-dir", str(runs_dir), "--new-run-id", "cfrr2"],
    )
    assert result.exit_code == 0, result.output
    assert len(captured) == 2
    assert captured[0].get("vep_cache") == "/v"
    assert captured[0].get("snpeff_cache") == "/s"
    assert captured[1].get("vep_cache") == "/v"
    assert captured[1].get("snpeff_cache") == "/s"
    assert "download_cache" not in captured[1]


def test_resume_replays_cache_inputs(tmp_path, monkeypatch):
    captured: list = []
    monkeypatch.setattr("contig.cli.self_heal_run", _self_heal_params_spy(captured))
    runs_dir = tmp_path / "runs"
    result = runner.invoke(
        app,
        ["run", "--run-id", "cfrs", "--runs-dir", str(runs_dir),
         "--pipeline", "nf-core/sarek", "--revision", "3.5.1",
         "--vep-cache", "/v", "--snpeff-cache", "/s"],
    )
    assert result.exit_code == 0, result.output
    (runs_dir / "cfrs" / "status.json").write_text(
        json.dumps({"run_id": "cfrs", "state": "cancelled", "pid": 4321,
                    "started_at": "2026-09-12T00:00:00+00:00",
                    "finished_at": "2026-09-12T00:01:00+00:00"})
    )
    result = runner.invoke(app, ["resume", "cfrs", "--runs-dir", str(runs_dir)])
    assert result.exit_code == 0, result.output
    assert len(captured) == 2
    assert captured[1].get("vep_cache") == "/v"
    assert captured[1].get("snpeff_cache") == "/s"
    assert "download_cache" not in captured[1]


def test_rerun_legacy_manifest_without_cache_inputs_dispatches_fine(tmp_path, monkeypatch):
    captured: list = []
    monkeypatch.setattr("contig.cli.self_heal_run", _self_heal_params_spy(captured))
    runs_dir = tmp_path / "runs"
    result = runner.invoke(
        app,
        ["run", "--run-id", "cfleg", "--runs-dir", str(runs_dir),
         "--pipeline", "nf-core/sarek", "--revision", "3.5.1"],
    )
    assert result.exit_code == 0, result.output
    launch_path = runs_dir / "cfleg" / "launch.json"
    launch = json.loads(launch_path.read_text())
    assert launch["vep_cache"] is None  # absent flags serialize as null
    # Simulate a pre-aspect manifest: strip the cache keys entirely, then a rerun
    # must still dispatch fine (the new fields default to None on parse).
    del launch["vep_cache"]
    del launch["snpeff_cache"]
    launch_path.write_text(json.dumps(launch))
    result = runner.invoke(
        app,
        ["rerun", "cfleg", "--runs-dir", str(runs_dir), "--new-run-id", "cfleg2"],
    )
    assert result.exit_code == 0, result.output
    assert len(captured) == 2
    assert captured[1].get("vep_cache") is None
    assert captured[1].get("snpeff_cache") is None
    assert captured[1].get("download_cache") == "true"  # status quo auto-download


# Task 4 -- argv tokens + refusal e2e ------------------------------------------


def test_cache_inputs_become_exact_argv_token_pairs():
    params = {"outdir": "/out", "vep_cache": "/v", "snpeff_cache": "/s"}
    cmd = build_nextflow_command(
        "nf-core/sarek", "3.5.1", ["docker"], "/trace", params=params
    )
    assert "--vep_cache" in cmd
    assert cmd[cmd.index("--vep_cache") + 1] == "/v"
    assert "--snpeff_cache" in cmd
    assert cmd[cmd.index("--snpeff_cache") + 1] == "/s"


def test_explicit_reference_refusal_launches_nothing(tmp_path, monkeypatch):
    sheet = _make_sheet(tmp_path)
    fasta, gtf = _make_overlapping_reference(tmp_path)
    captured: list = []
    monkeypatch.setattr("contig.cli.self_heal_run", _self_heal_params_spy(captured))
    runs_dir = tmp_path / "runs"
    result = runner.invoke(
        app,
        ["run", "--run-id", "exref", "--runs-dir", str(runs_dir),
         "--pipeline", "nf-core/sarek", "--revision", "3.5.1",
         "--input", str(sheet), "--fasta", str(fasta), "--gtf", str(gtf)],
    )
    assert result.exit_code == 1
    assert "--vep-cache" in result.output
    assert "--snpeff-cache" in result.output
    assert len(captured) == 0  # self_heal_run never entered
    assert not (runs_dir / "exref" / "launch.json").exists()  # no launch artifact
    assert not (runs_dir / "caches").exists()  # refusal before any cache dir