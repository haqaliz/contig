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


def test_run_absolutizes_relative_input_path(tmp_path, monkeypatch):
    # Given a relative --input, the stored param must be absolute (Nextflow runs
    # with cwd=run_dir, so a relative sheet path would fail nf-core validation).
    _make_sheet(tmp_path)
    monkeypatch.setattr("contig.cli.default_executor", _fake_run_executor(TRACE_RUN_OK, GOOD_MQC))
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(
        app,
        ["run", "--run-id", "rel", "--runs-dir", "runs",
         "--input", "samplesheet.csv", "--genome", "GRCh38"],
    )
    assert result.exit_code == 0
    rec = load_bundle(tmp_path / "runs" / "rel")
    stored = rec.parameters.get("input")
    assert stored.startswith("/") and stored.endswith("samplesheet.csv")


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


def test_run_defaults_outdir_under_run_dir(tmp_path, monkeypatch):
    # nf-core always requires --outdir; Contig must default it so a bare run works.
    monkeypatch.setattr("contig.cli.default_executor", _fake_run_executor(TRACE_RUN_OK, GOOD_MQC))
    runner.invoke(app, ["run", "--run-id", "od", "--runs-dir", str(tmp_path / "runs")])
    rec = load_bundle(tmp_path / "runs" / "od")
    outdir = rec.parameters.get("outdir")
    assert outdir and "od" in outdir and outdir.endswith("results")
    assert outdir.startswith("/")  # absolute (Nextflow runs in the run dir)


def test_run_caps_emit_resourcelimits_not_ignored_params(tmp_path, monkeypatch):
    # Modern nf-core ignores --max_memory/--max_cpus params; caps must ride in
    # the generated config as process.resourceLimits.
    sheet = _make_sheet(tmp_path)
    monkeypatch.setattr("contig.cli.default_executor", _fake_run_executor(TRACE_RUN_OK, GOOD_MQC))
    runner.invoke(
        app,
        ["run", "--run-id", "rc", "--runs-dir", str(tmp_path / "runs"),
         "--input", str(sheet), "--genome", "GRCh38",
         "--max-memory", "6.GB", "--max-cpus", "2"],
    )
    config = (tmp_path / "runs" / "rc" / "nextflow.config").read_text()
    assert "process.resourceLimits = [ memory: 6.GB, cpus: 2 ]" in config
    # the ignored params must NOT be passed
    rec = load_bundle(tmp_path / "runs" / "rc")
    assert "max_memory" not in rec.parameters
    assert "max_cpus" not in rec.parameters


def test_run_rejects_conflicting_reference(tmp_path):
    sheet = _make_sheet(tmp_path)
    result = runner.invoke(
        app,
        ["run", "--run-id", "r", "--runs-dir", str(tmp_path / "runs"),
         "--input", str(sheet), "--genome", "GRCh38", "--fasta", "x.fa", "--gtf", "x.gtf"],
    )
    assert result.exit_code != 0


VARIANT_MQC = '{"report_general_stats_data":[{"S1":{"ts_tv":2.05,"het_hom":1.6,"mean_coverage":35.0}}]}'


def test_run_uses_variant_qc_for_sarek_pipeline(tmp_path, monkeypatch):
    monkeypatch.setattr("contig.cli.default_executor", _fake_run_executor(TRACE_RUN_OK, VARIANT_MQC))
    result = runner.invoke(
        app,
        ["run", "--run-id", "v", "--runs-dir", str(tmp_path),
         "--pipeline", "nf-core/sarek", "--revision", "3.5.1"],
    )
    assert result.exit_code == 0
    assert "ts_tv_ratio" in result.output  # variant rule pack was applied


def test_run_on_aws_batch_generates_awsbatch_config(tmp_path, monkeypatch):
    # P6: a user reaches the second compute backend by naming it + its queue/region.
    monkeypatch.setattr("contig.cli.default_executor", _fake_run_executor(TRACE_RUN_OK, GOOD_MQC))
    result = runner.invoke(
        app,
        ["run", "--run-id", "aws", "--runs-dir", str(tmp_path),
         "--backend", "aws_batch", "--work-dir", "s3://contig/work",
         "--queue", "contig-q", "--region", "eu-west-1"],
    )
    assert result.exit_code == 0
    config = (tmp_path / "aws" / "nextflow.config").read_text()
    assert "process.executor = 'awsbatch'" in config
    assert "process.queue = 'contig-q'" in config
    assert "workDir = 's3://contig/work'" in config


def test_run_aws_batch_without_queue_fails_cleanly(tmp_path, monkeypatch):
    # Missing required backend options must be a clear error, not a traceback.
    monkeypatch.setattr("contig.cli.default_executor", _fake_run_executor(TRACE_RUN_OK, GOOD_MQC))
    result = runner.invoke(
        app,
        ["run", "--run-id", "aws", "--runs-dir", str(tmp_path),
         "--backend", "aws_batch", "--work-dir", "s3://contig/work"],
    )
    assert result.exit_code != 0
    assert "queue" in result.output.lower()
    assert result.exception is None or isinstance(result.exception, SystemExit)


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


def test_eval_detector_scores_the_shipped_corpus(tmp_path):
    result = runner.invoke(app, ["eval-detector"])
    assert result.exit_code == 0
    assert "accuracy" in result.output.lower()
    assert "bad_param" in result.output  # per-class breakdown shown


def test_eval_detector_reports_a_miss_for_a_mislabeled_case(tmp_path):
    from contig.corpus import save_corpus
    from contig.models import FailureCase, TaskEvent

    corpus = tmp_path / "c.jsonl"
    save_corpus(
        [FailureCase(case_id="bogus", description="d", source="t",
                     events=[TaskEvent(process="X", status="FAILED", exit=1)],
                     log_text="Segmentation fault", expected_class="oom")],
        corpus,
    )
    result = runner.invoke(app, ["eval-detector", "--corpus", str(corpus)])
    assert result.exit_code == 0
    assert "bogus" in result.output and "tool_crash" in result.output


def test_version_prints_package_version():
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "0.0.1" in result.output


def test_plan_proposes_rnaseq_for_a_de_goal(tmp_path):
    sheet = _make_sheet(tmp_path)
    result = runner.invoke(
        app,
        ["plan", "--goal", "find differentially expressed genes",
         "--input", str(sheet), "--genome", "GRCh38"],
    )
    assert result.exit_code == 0
    assert "nf-core/rnaseq" in result.output
    assert "GRCh38" in result.output


def test_plan_warns_about_replicates_on_single_sample(tmp_path):
    sheet = _make_sheet(tmp_path)  # one sample
    result = runner.invoke(
        app,
        ["plan", "--goal", "RNA-seq differential expression",
         "--input", str(sheet), "--genome", "GRCh38"],
    )
    assert result.exit_code == 0
    assert "replicates" in result.output


def test_plan_rejects_an_unrecognized_goal(tmp_path):
    sheet = _make_sheet(tmp_path)
    result = runner.invoke(
        app, ["plan", "--goal", "assemble a de novo bacterial genome", "--input", str(sheet)]
    )
    assert result.exit_code != 0
