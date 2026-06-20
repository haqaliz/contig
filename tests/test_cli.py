from pathlib import Path

from typer.testing import CliRunner

from contig.bundle import load_bundle, write_bundle
from contig.cli import app
from contig.models import ExecutionTarget, RunRecord, TaskEvent


def _make_sheet(tmp_path, *, valid=True):
    (tmp_path / "s1_R1.fastq.gz").write_bytes(b"\x1f\x8bR1")
    (tmp_path / "s1_R2.fastq.gz").write_bytes(b"\x1f\x8bR2")
    sheet = tmp_path / "samplesheet.csv"
    r1 = "s1_R1.fastq.gz" if valid else "missing_R1.fastq.gz"
    sheet.write_text(f"sample,fastq_1,fastq_2,strandedness\nS1,{r1},s1_R2.fastq.gz,auto\n")
    return sheet

runner = CliRunner()

GOOD_MQC = (
    '{"report_general_stats_data":[{'
    '"S1":{"uniquely_mapped_percent":92.0,"percent_assigned":85.0,"total_reads":1000000.0},'
    '"S2":{"uniquely_mapped_percent":90.0,"percent_assigned":84.0,"total_reads":1100000.0}}]}'
)
TRACE_OK = (
    "task_id\thash\tnative_id\tname\tstatus\texit\tsubmit\tduration\trealtime\n"
    "1\tab/cd\t1\tFASTQC (S1)\tCOMPLETED\t0\t-\t-\t-\n"
)
TRACE_FAIL = (  # unrecoverable tool crash (exit 1) -> self-heal gives up in one attempt
    "task_id\thash\tnative_id\tname\tstatus\texit\tsubmit\tduration\trealtime\n"
    "1\tab/cd\t1\tSTAR (S1)\tFAILED\t1\t-\t-\t-\n"
)
TRACE_OOM = (  # exit 137 -> OOM -> a safe resource patch the loop can auto-apply
    "task_id\thash\tnative_id\tname\tstatus\texit\tsubmit\tduration\trealtime\n"
    "1\tab/cd\t1\tSTAR (S1)\tFAILED\t137\t-\t-\t-\n"
)
TRACE_RUN_OK = (
    "task_id\thash\tnative_id\tname\tstatus\texit\tsubmit\tduration\trealtime\n"
    "1\tab/cd\t1\tSTAR (S1)\tCOMPLETED\t0\t-\t-\t-\n"
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


def test_run_with_samplesheet_checksums_real_inputs(tmp_path, monkeypatch):
    sheet = _make_sheet(tmp_path)
    monkeypatch.setattr("contig.cli.default_executor", _fake_run_executor(TRACE_RUN_OK, GOOD_MQC))
    result = runner.invoke(
        app,
        ["run", "--run-id", "real", "--runs-dir", str(tmp_path / "runs"),
         "--input", str(sheet), "--genome", "GRCh38"],
    )
    assert result.exit_code == 0
    rec = load_bundle(tmp_path / "runs" / "real")
    assert "samplesheet.csv" in rec.input_checksums
    assert "s1_R1.fastq.gz" in rec.input_checksums
    assert "s1_R2.fastq.gz" in rec.input_checksums
    assert rec.parameters.get("genome") == "GRCh38"
    assert rec.parameters.get("input")


def test_run_rejects_malformed_samplesheet_without_launching(tmp_path, monkeypatch):
    sheet = _make_sheet(tmp_path, valid=False)  # references a non-existent FASTQ
    launched = {"n": 0}

    def exec_spy(cmd, trace_path):
        launched["n"] += 1
        Path(trace_path).write_text(TRACE_RUN_OK)
        return 0

    monkeypatch.setattr("contig.cli.default_executor", exec_spy)
    result = runner.invoke(
        app,
        ["run", "--run-id", "bad", "--runs-dir", str(tmp_path / "runs"),
         "--input", str(sheet), "--genome", "GRCh38"],
    )
    assert result.exit_code != 0
    assert "not found" in result.output.lower()
    assert launched["n"] == 0  # pre-flight rejected it; the pipeline never launched


def test_run_rejects_conflicting_reference(tmp_path):
    sheet = _make_sheet(tmp_path)
    result = runner.invoke(
        app,
        ["run", "--run-id", "r", "--runs-dir", str(tmp_path / "runs"),
         "--input", str(sheet), "--genome", "GRCh38", "--fasta", "x.fa", "--gtf", "x.gtf"],
    )
    assert result.exit_code != 0


def test_run_self_heals_oom_and_shows_repair_chain(tmp_path, monkeypatch):
    state = {"n": 0}

    def executor(cmd, trace_path):
        state["n"] += 1
        p = Path(trace_path)
        if state["n"] == 1:
            p.write_text(TRACE_OOM)
            (p.parent / "run.log").write_text("Process killed: out of memory (exit 137)")
            return 1
        p.write_text(TRACE_RUN_OK)
        (p.parent / "run.log").write_text("ok")
        return 0

    monkeypatch.setattr("contig.cli.default_executor", executor)
    result = runner.invoke(app, ["run", "--run-id", "h", "--runs-dir", str(tmp_path)])
    assert result.exit_code == 0
    assert "oom" in result.output.lower()
    assert "patched_and_retried" in result.output


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
