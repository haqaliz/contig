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