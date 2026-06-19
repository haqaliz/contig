from pathlib import Path

from typer.testing import CliRunner

from contig.bundle import write_bundle
from contig.cli import app
from contig.models import ExecutionTarget, RunRecord, TaskEvent

runner = CliRunner()

GOOD_MQC = '{"report_general_stats_data":[{"S1":{"uniquely_mapped_percent":92.0,"percent_assigned":85.0}}]}'
TRACE_OK = (
    "task_id\thash\tnative_id\tname\tstatus\texit\tsubmit\tduration\trealtime\n"
    "1\tab/cd\t1\tFASTQC (S1)\tCOMPLETED\t0\t-\t-\t-\n"
)
TRACE_FAIL = (
    "task_id\thash\tnative_id\tname\tstatus\texit\tsubmit\tduration\trealtime\n"
    "1\tab/cd\t1\tSTAR (S1)\tFAILED\t137\t-\t-\t-\n"
)


def _write_run(runs_dir, run_id, events):
    record = RunRecord(
        run_id=run_id,
        pipeline="nf-core/rnaseq",
        pipeline_revision="3.26.0",
        target=ExecutionTarget(backend="local", container_runtime="docker", work_dir="w"),
        input_checksums={},
        events=events,
    )
    write_bundle(record, Path(runs_dir) / run_id)


def _fake_run_executor(trace_text, mqc_json=None):
    def execute(cmd, trace_path):
        Path(trace_path).write_text(trace_text)
        if mqc_json is not None:
            d = Path(trace_path).parent / "results" / "multiqc"
            d.mkdir(parents=True, exist_ok=True)
            (d / "multiqc_data.json").write_text(mqc_json)
        return 0 if mqc_json is not None else 1
    return execute


def test_show_prints_verdict_for_existing_run(tmp_path):
    _write_run(tmp_path, "r1", [TaskEvent(process="X", status="COMPLETED", exit=0)])
    result = runner.invoke(app, ["show", "r1", "--runs-dir", str(tmp_path)])
    assert result.exit_code == 0
    assert "VERDICT" in result.output


def test_show_errors_on_missing_run(tmp_path):
    result = runner.invoke(app, ["show", "nope", "--runs-dir", str(tmp_path)])
    assert result.exit_code != 0


def test_list_shows_bundled_run_ids(tmp_path):
    _write_run(tmp_path, "r1", [TaskEvent(process="X", status="COMPLETED", exit=0)])
    _write_run(tmp_path, "r2", [TaskEvent(process="X", status="COMPLETED", exit=0)])
    result = runner.invoke(app, ["list", "--runs-dir", str(tmp_path)])
    assert result.exit_code == 0
    assert "r1" in result.output and "r2" in result.output


def test_run_executes_and_prints_pass_verdict(tmp_path, monkeypatch):
    monkeypatch.setattr("contig.cli.default_executor", _fake_run_executor(TRACE_OK, GOOD_MQC))
    result = runner.invoke(app, ["run", "--run-id", "r1", "--runs-dir", str(tmp_path)])
    assert result.exit_code == 0
    assert "PASS" in result.output


def test_run_reports_failure_but_still_captures_bundle(tmp_path, monkeypatch):
    monkeypatch.setattr("contig.cli.default_executor", _fake_run_executor(TRACE_FAIL))
    result = runner.invoke(app, ["run", "--run-id", "rf", "--runs-dir", str(tmp_path)])
    assert result.exit_code != 0
    assert "FAIL" in result.output
    # the bundle was still written despite the failure
    assert (tmp_path / "rf" / "run_record.json").exists()


def test_version_prints_package_version():
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "0.0.1" in result.output


def test_plan_shows_default_pipeline():
    result = runner.invoke(app, ["plan", "--work-dir", "/tmp/run"])
    assert result.exit_code == 0
    assert "nf-core/rnaseq" in result.output


def test_plan_mentions_chosen_backend():
    result = runner.invoke(app, ["plan", "--work-dir", "/tmp/run", "--backend", "slurm"])
    assert result.exit_code == 0
    assert "slurm" in result.output


def test_plan_rejects_invalid_backend():
    result = runner.invoke(app, ["plan", "--work-dir", "/tmp/run", "--backend", "bogus"])
    assert result.exit_code != 0


def test_plan_echoes_custom_pipeline():
    result = runner.invoke(
        app, ["plan", "--work-dir", "/tmp/run", "--pipeline", "nf-core/sarek"]
    )
    assert result.exit_code == 0
    assert "nf-core/sarek" in result.output
