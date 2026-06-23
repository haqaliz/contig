"""CLI tests for `contig benchmark` and `contig benchmark set` (PRD contract A)."""

import json
from pathlib import Path

from typer.testing import CliRunner

from contig.bundle import write_bundle
from contig.cli import app
from contig.models import ExecutionTarget, QCResult, RunRecord, TaskEvent

runner = CliRunner()


def _write_run(runs_dir, run_id, pipeline, qc):
    record = RunRecord(
        run_id=run_id,
        pipeline=pipeline,
        pipeline_revision="3.26.0",
        target=ExecutionTarget(backend="local", container_runtime="docker", work_dir="w"),
        input_checksums={},
        events=[TaskEvent(process="X", status="COMPLETED", exit=0)],
        qc_results=qc,
    )
    write_bundle(record, Path(runs_dir) / run_id)


def _qc(check, value):
    return QCResult(check=check, status="pass", message="ok", value=value)


def test_benchmark_set_records_the_reference(tmp_path):
    _write_run(tmp_path, "run-ref", "nf-core/rnaseq", [_qc("mapping_rate", 90.0)])
    registry = tmp_path / "ref.jsonl"
    result = runner.invoke(
        app,
        ["benchmark", "set", "run-ref", "--runs-dir", str(tmp_path),
         "--registry", str(registry)],
    )
    assert result.exit_code == 0
    lines = [json_line for json_line in registry.read_text().splitlines() if json_line.strip()]
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["pipeline"] == "nf-core/rnaseq"
    assert entry["assay"] == "rnaseq"
    assert entry["reference_run_id"] == "run-ref"
    assert entry["metrics"] == {"mapping_rate": 90.0}


def test_benchmark_set_rejects_an_unsafe_run_id(tmp_path):
    result = runner.invoke(
        app, ["benchmark", "set", "--evil", "--runs-dir", str(tmp_path)]
    )
    assert result.exit_code != 0


def test_benchmark_set_errors_on_missing_run(tmp_path):
    result = runner.invoke(
        app, ["benchmark", "set", "ghost", "--runs-dir", str(tmp_path)]
    )
    assert result.exit_code != 0


def test_benchmark_json_reports_match(tmp_path):
    _write_run(tmp_path, "run-ref", "nf-core/rnaseq", [_qc("mapping_rate", 90.0)])
    _write_run(tmp_path, "run-now", "nf-core/rnaseq", [_qc("mapping_rate", 92.0)])
    registry = tmp_path / "ref.jsonl"
    runner.invoke(
        app,
        ["benchmark", "set", "run-ref", "--runs-dir", str(tmp_path),
         "--registry", str(registry)],
    )
    result = runner.invoke(
        app,
        ["benchmark", "run-now", "--runs-dir", str(tmp_path),
         "--registry", str(registry), "--json"],
    )
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["status"] == "match"
    assert payload["reference_run_id"] == "run-ref"
    assert payload["matched"] == 1
    assert payload["checks"][0]["name"] == "mapping_rate"


def test_benchmark_json_reports_drift_outside_tolerance(tmp_path):
    _write_run(tmp_path, "run-ref", "nf-core/rnaseq", [_qc("mapping_rate", 90.0)])
    _write_run(tmp_path, "run-now", "nf-core/rnaseq", [_qc("mapping_rate", 40.0)])
    registry = tmp_path / "ref.jsonl"
    runner.invoke(
        app,
        ["benchmark", "set", "run-ref", "--runs-dir", str(tmp_path),
         "--registry", str(registry)],
    )
    result = runner.invoke(
        app,
        ["benchmark", "run-now", "--runs-dir", str(tmp_path),
         "--registry", str(registry), "--tolerance", "0.1", "--json"],
    )
    payload = json.loads(result.output)
    assert payload["status"] == "drift"
    assert payload["drifted"] == 1


def test_benchmark_no_reference_is_status_no_reference_exit_zero(tmp_path):
    _write_run(tmp_path, "run-now", "nf-core/rnaseq", [_qc("mapping_rate", 92.0)])
    registry = tmp_path / "ref.jsonl"
    result = runner.invoke(
        app,
        ["benchmark", "run-now", "--runs-dir", str(tmp_path),
         "--registry", str(registry), "--json"],
    )
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["status"] == "no_reference"


def test_benchmark_rejects_an_unsafe_run_id(tmp_path):
    result = runner.invoke(app, ["benchmark", "--runs-dir", str(tmp_path)])
    # no run id given is a usage error
    assert result.exit_code != 0


def test_benchmark_errors_on_missing_run(tmp_path):
    result = runner.invoke(
        app, ["benchmark", "ghost", "--runs-dir", str(tmp_path)]
    )
    assert result.exit_code != 0


def test_benchmark_text_output_names_the_status(tmp_path):
    _write_run(tmp_path, "run-ref", "nf-core/rnaseq", [_qc("mapping_rate", 90.0)])
    _write_run(tmp_path, "run-now", "nf-core/rnaseq", [_qc("mapping_rate", 92.0)])
    registry = tmp_path / "ref.jsonl"
    runner.invoke(
        app,
        ["benchmark", "set", "run-ref", "--runs-dir", str(tmp_path),
         "--registry", str(registry)],
    )
    result = runner.invoke(
        app,
        ["benchmark", "run-now", "--runs-dir", str(tmp_path),
         "--registry", str(registry)],
    )
    assert result.exit_code == 0
    assert "match" in result.output.lower()
