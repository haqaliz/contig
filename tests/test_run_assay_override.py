"""Phase 1 (M2/M9): an explicit --assay overrides the pipeline-derived assay.

The run's assay becomes an explicit, persisted input that WINS OVER the legacy
`assay_for_pipeline(pipeline) or "rnaseq"` derivation (which fixes the
nf-core/sarek somatic-vs-germline pipeline-string collision), while the legacy
derivation stays intact as the fallback so existing runs and shipped bundles are
unaffected (backward-compat).
"""

import json
from pathlib import Path

from typer.testing import CliRunner

from contig.bundle import load_bundle
from contig.cli import app
from contig.models import ExecutionTarget, LaunchManifest, RunRecord

runner = CliRunner()

TRACE_RUN_OK = (
    "task_id\thash\tnative_id\tname\tstatus\texit\tsubmit\tduration\trealtime\n"
    "1\tab/cd\t1\tSTAR (S1)\tCOMPLETED\t0\t-\t-\t-\n"
)
VARIANT_MQC = '{"report_general_stats_data":[{"S1":{"ts_tv":2.05,"het_hom":1.6,"mean_coverage":35.0}}]}'


def _fake_run_executor(trace_text, mqc_json=None):
    def execute(cmd, trace_path):
        Path(trace_path).write_text(trace_text)
        if mqc_json is not None:
            d = Path(trace_path).parent / "results" / "multiqc"
            d.mkdir(parents=True, exist_ok=True)
            (d / "multiqc_data.json").write_text(mqc_json)
        return 0 if mqc_json is not None else 1
    return execute


def _self_heal_spy(captured):
    """A stand-in for self_heal_run that records the assay it was handed and
    returns a minimal valid RunRecord so the CLI can render its report."""

    def spy(**kwargs):
        captured.append(kwargs.get("assay"))
        return RunRecord(
            run_id=kwargs["run_id"],
            pipeline=kwargs["pipeline"],
            pipeline_revision=kwargs["revision"],
            target=kwargs["target"],
            input_checksums={},
        )

    return spy


# (a) explicit --assay wins over the pipeline-derived assay ---------------------


def test_explicit_assay_overrides_pipeline_derived(tmp_path, monkeypatch):
    captured: list = []
    monkeypatch.setattr("contig.cli.self_heal_run", _self_heal_spy(captured))
    result = runner.invoke(
        app,
        ["run", "--run-id", "s", "--runs-dir", str(tmp_path),
         "--pipeline", "nf-core/sarek", "--revision", "3.5.1",
         "--assay", "somatic_variant_calling"],
    )
    assert result.exit_code == 0, result.output
    # sarek would otherwise derive "variant_calling"; the explicit assay wins.
    assert captured == ["somatic_variant_calling"]


# (b) germline-unchanged regression: no --assay => legacy derivation ------------


def test_sarek_without_assay_still_resolves_variant_calling(tmp_path, monkeypatch):
    captured: list = []
    monkeypatch.setattr("contig.cli.self_heal_run", _self_heal_spy(captured))
    result = runner.invoke(
        app,
        ["run", "--run-id", "g", "--runs-dir", str(tmp_path),
         "--pipeline", "nf-core/sarek", "--revision", "3.5.1"],
    )
    assert result.exit_code == 0, result.output
    assert captured == ["variant_calling"]


def test_rnaseq_without_assay_still_resolves_rnaseq(tmp_path, monkeypatch):
    captured: list = []
    monkeypatch.setattr("contig.cli.self_heal_run", _self_heal_spy(captured))
    result = runner.invoke(
        app,
        ["run", "--run-id", "r", "--runs-dir", str(tmp_path),
         "--pipeline", "nf-core/rnaseq"],
    )
    assert result.exit_code == 0, result.output
    assert captured == ["rnaseq"]


# (c) backward-compat: legacy manifest / record without an assay field ----------


def test_legacy_launch_manifest_without_assay_loads(tmp_path):
    legacy = json.dumps({
        "run_id": "old",
        "pipeline": "nf-core/sarek",
        "revision": "3.5.1",
        "profiles": ["docker"],
        "backend": "local",
        "container_runtime": "docker",
        "created_at": "2026-01-01T00:00:00+00:00",
    })
    manifest = LaunchManifest.model_validate_json(legacy)
    assert manifest.assay is None  # optional -> defaulted, no error


def test_legacy_run_record_without_assay_loads():
    legacy = {
        "run_id": "old",
        "pipeline": "nf-core/sarek",
        "pipeline_revision": "3.5.1",
        "target": {"backend": "local", "container_runtime": "docker", "work_dir": "w"},
        "input_checksums": {},
    }
    record = RunRecord.model_validate(legacy)
    assert record.assay is None  # optional -> defaulted, no error


# resolved assay is persisted on both the record and the manifest ---------------


def test_run_persists_resolved_assay_on_record_and_manifest(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "contig.cli.default_executor", _fake_run_executor(TRACE_RUN_OK, VARIANT_MQC)
    )
    result = runner.invoke(
        app,
        ["run", "--run-id", "p", "--runs-dir", str(tmp_path),
         "--pipeline", "nf-core/sarek", "--revision", "3.5.1",
         "--assay", "somatic_variant_calling"],
    )
    assert result.exit_code == 0, result.output
    manifest = json.loads((tmp_path / "p" / "launch.json").read_text())
    assert manifest["assay"] == "somatic_variant_calling"
    record = load_bundle(tmp_path / "p")
    assert record.assay == "somatic_variant_calling"


# (d) rerun replays the persisted assay ----------------------------------------


def test_rerun_replays_persisted_assay(tmp_path, monkeypatch):
    captured: list = []
    monkeypatch.setattr("contig.cli.self_heal_run", _self_heal_spy(captured))
    runs_dir = tmp_path / "runs"
    runner.invoke(
        app,
        ["run", "--run-id", "orig", "--runs-dir", str(runs_dir),
         "--pipeline", "nf-core/sarek", "--revision", "3.5.1",
         "--assay", "somatic_variant_calling"],
    )
    result = runner.invoke(
        app,
        ["rerun", "orig", "--runs-dir", str(runs_dir), "--new-run-id", "copy"],
    )
    assert result.exit_code == 0, result.output
    # both the original and the replay resolved the persisted somatic assay
    assert captured == ["somatic_variant_calling", "somatic_variant_calling"]
    new_manifest = json.loads((runs_dir / "copy" / "launch.json").read_text())
    assert new_manifest["assay"] == "somatic_variant_calling"
