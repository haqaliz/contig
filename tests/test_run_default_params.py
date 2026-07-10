"""Phase 4 (M4): a per-assay declarative default_params seam injects `--tools`.

A somatic sarek run must genuinely invoke sarek's somatic callers, so the
resolved assay's registry `default_params`
(e.g. `{"tools": "strelka,mutect2,vep"}`)
are merged into the run's `params` — WITHOUT overriding a user-supplied value —
before the launch manifest is written and before self-heal runs. Every other
assay keeps an empty default, so germline/RNA-seq command assembly is unchanged.

Scope (R5, honest): this proves the COMMAND IS CORRECTLY ASSEMBLED (the
`--tools` flag rides into the Nextflow argv and reproduces), NOT that a real
somatic run completes — Mutect2 typically needs a panel-of-normals / germline
resource that `resolve_reference` does not wire. That wiring is deferred.
"""

import json
from pathlib import Path

from typer.testing import CliRunner

from contig.cli import _inject_default_params, app
from contig.models import RunRecord
from contig.registry import select_pipeline
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


# (a) a somatic run injects --tools strelka,mutect2,vep ----------------------------


def test_somatic_run_injects_tools_into_params(tmp_path, monkeypatch):
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
    assert captured[0].get("tools") == "strelka,mutect2,vep"


def test_somatic_command_carries_tools_flag():
    """The merged param becomes `--tools strelka,mutect2,vep` in the Nextflow argv."""
    params = {"outdir": "/out", "tools": "strelka,mutect2,vep"}
    cmd = build_nextflow_command(
        "nf-core/sarek", "3.5.1", ["docker"], "/trace", params=params
    )
    assert "--tools" in cmd
    assert cmd[cmd.index("--tools") + 1] == "strelka,mutect2,vep"


# (b) germline injects annotation tools; RNA-seq keeps an empty default => no --tools


def test_germline_sarek_run_injects_annotation_tools(tmp_path, monkeypatch):
    """Germline now enables sarek's built-in annotation step (VEP -> CSQ) alongside
    the caller (capability C7), so a germline run injects --tools haplotypecaller,vep
    — mirroring how somatic injects strelka,mutect2."""
    captured: list = []
    monkeypatch.setattr("contig.cli.self_heal_run", _self_heal_params_spy(captured))
    result = runner.invoke(
        app,
        ["run", "--run-id", "g", "--runs-dir", str(tmp_path),
         "--pipeline", "nf-core/sarek", "--revision", "3.5.1"],
    )
    assert result.exit_code == 0, result.output
    assert captured and captured[0] is not None
    assert captured[0].get("tools") == "haplotypecaller,vep"


def test_rnaseq_run_injects_no_tools(tmp_path, monkeypatch):
    captured: list = []
    monkeypatch.setattr("contig.cli.self_heal_run", _self_heal_params_spy(captured))
    result = runner.invoke(
        app,
        ["run", "--run-id", "r", "--runs-dir", str(tmp_path),
         "--pipeline", "nf-core/rnaseq"],
    )
    assert result.exit_code == 0, result.output
    assert captured and captured[0] is not None
    assert "tools" not in captured[0]


# (c) reproduce carries the injected --tools ---------------------------------------


def test_rerun_reinjects_tools_via_persisted_assay(tmp_path, monkeypatch):
    """launch.json persists the somatic assay; a rerun re-enters dispatch and the
    registry default_params re-inject --tools, so reproduce is faithful."""
    captured: list = []
    monkeypatch.setattr("contig.cli.self_heal_run", _self_heal_params_spy(captured))
    runs_dir = tmp_path / "runs"
    runner.invoke(
        app,
        ["run", "--run-id", "orig", "--runs-dir", str(runs_dir),
         "--pipeline", "nf-core/sarek", "--revision", "3.5.1",
         "--assay", "somatic_variant_calling"],
    )
    # the persisted assay is what carries the tools default across reproduce
    manifest = json.loads((runs_dir / "orig" / "launch.json").read_text())
    assert manifest["assay"] == "somatic_variant_calling"

    result = runner.invoke(
        app,
        ["rerun", "orig", "--runs-dir", str(runs_dir), "--new-run-id", "copy"],
    )
    assert result.exit_code == 0, result.output
    # both the original run and the replay assembled --tools
    assert len(captured) == 2
    assert captured[0].get("tools") == "strelka,mutect2,vep"
    assert captured[1].get("tools") == "strelka,mutect2,vep"


# (d) merge never clobbers an already-present (user) param -------------------------


def test_inject_default_params_does_not_override_existing_key():
    params = {"tools": "user_choice", "outdir": "/out"}
    _inject_default_params(params, "somatic_variant_calling")
    assert params["tools"] == "user_choice"  # user value wins, default does not clobber


def test_inject_default_params_adds_registry_default():
    params: dict[str, object] = {"outdir": "/out"}
    _inject_default_params(params, "somatic_variant_calling")
    assert params["tools"] == "strelka,mutect2,vep"


def test_inject_default_params_empty_for_non_somatic():
    params: dict[str, object] = {"outdir": "/out"}
    _inject_default_params(params, "rnaseq")
    assert "tools" not in params


def test_inject_default_params_unregistered_assay_is_noop():
    params: dict[str, object] = {"outdir": "/out"}
    _inject_default_params(params, "not_a_real_assay")  # must not raise
    assert params == {"outdir": "/out"}


def test_pipeline_entry_default_params_empty_by_default():
    # every non-somatic entry keeps an empty default (no behavior change)
    assert select_pipeline("rnaseq").default_params == {}
    # Germline now enables sarek's built-in annotation step (VEP) alongside the
    # caller (capability C7) — no longer an empty default.
    assert select_pipeline("variant_calling").default_params == {"tools": "haplotypecaller,vep"}
    # Somatic now also enables sarek's built-in annotation step (VEP -> CSQ)
    # alongside the somatic callers (capability C7, M2).
    assert select_pipeline("somatic_variant_calling").default_params == {
        "tools": "strelka,mutect2,vep"
    }
