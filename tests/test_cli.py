import json
from pathlib import Path

from typer.testing import CliRunner

from contig.bundle import load_bundle, write_bundle
from contig.cli import app
from contig.models import ExecutionTarget, QCResult, RunRecord, TaskEvent, TaskResource


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


def test_show_html_prints_html_document(tmp_path):
    _write_run(tmp_path, "r1", [TaskEvent(process="X", status="COMPLETED", exit=0)])
    result = runner.invoke(app, ["show", "r1", "--runs-dir", str(tmp_path), "--html"])
    assert result.exit_code == 0
    assert "<html" in result.output.lower()


def test_show_html_writes_to_output_file(tmp_path):
    _write_run(tmp_path, "r1", [TaskEvent(process="X", status="COMPLETED", exit=0)])
    out = tmp_path / "report.html"
    result = runner.invoke(
        app,
        ["show", "r1", "--runs-dir", str(tmp_path), "--html", "--output", str(out)],
    )
    assert result.exit_code == 0
    assert "<html" in out.read_text().lower()
    # the whole document is not dumped to stdout when written to a file
    assert "<html" not in result.output.lower()


def test_show_explain_names_the_deciding_check(tmp_path):
    from contig.models import QCResult

    record = RunRecord(
        run_id="ex",
        pipeline="nf-core/rnaseq",
        pipeline_revision="3.26.0",
        target=ExecutionTarget(backend="local", container_runtime="docker", work_dir="w"),
        input_checksums={},
        events=[TaskEvent(process="X", status="COMPLETED", exit=0)],
        qc_results=[
            QCResult(check="salmon_mapping_rate", status="warn", message="low",
                     value=58.1, expected_range=">= 60.0"),
        ],
    )
    write_bundle(record, Path(tmp_path) / "ex")
    result = runner.invoke(app, ["show", "ex", "--runs-dir", str(tmp_path), "--explain"])
    assert result.exit_code == 0
    assert "WARN" in result.output
    assert "salmon_mapping_rate" in result.output
    assert ">= 60.0" in result.output


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
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKIAEXAMPLE")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "secret")
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


def test_run_aws_batch_refuses_without_credentials(tmp_path, monkeypatch):
    # PRD contract E: a misconfigured AWS Batch launch is refused by the preflight
    # BEFORE Nextflow is ever invoked. No credentials -> refuse, executor untouched.
    launched = {"n": 0}

    def spy(cmd, trace_path):
        launched["n"] += 1
        return 0

    monkeypatch.setattr("contig.cli.default_executor", spy)
    for var in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_PROFILE"):
        monkeypatch.delenv(var, raising=False)
    result = runner.invoke(
        app,
        ["run", "--run-id", "awsbad", "--runs-dir", str(tmp_path),
         "--backend", "aws_batch", "--work-dir", "s3://contig/work",
         "--queue", "contig-q", "--region", "eu-west-1"],
    )
    assert result.exit_code != 0
    assert "credential" in result.output.lower()
    assert launched["n"] == 0  # refused before any launch


def test_run_aws_batch_refuses_non_s3_work_dir(tmp_path, monkeypatch):
    monkeypatch.setattr("contig.cli.default_executor", _fake_run_executor(TRACE_RUN_OK, GOOD_MQC))
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKIAEXAMPLE")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "secret")
    result = runner.invoke(
        app,
        ["run", "--run-id", "awslocal", "--runs-dir", str(tmp_path),
         "--backend", "aws_batch", "--work-dir", "/local/work",
         "--queue", "contig-q", "--region", "eu-west-1"],
    )
    assert result.exit_code != 0
    assert "s3://" in result.output


def test_run_on_slurm_generates_slurm_config(tmp_path, monkeypatch):
    # A user reaches the HPC backend by naming it + its partition (via --queue)
    # and account (via --opt). sbatch/sinfo present so the preflight passes.
    monkeypatch.setattr("contig.cli.default_executor", _fake_run_executor(TRACE_RUN_OK, GOOD_MQC))
    monkeypatch.setattr("contig.cli.shutil.which", lambda name: f"/usr/bin/{name}")
    result = runner.invoke(
        app,
        ["run", "--run-id", "slurm", "--runs-dir", str(tmp_path),
         "--backend", "slurm", "--container-runtime", "singularity",
         "--queue", "general", "--opt", "account=lab"],
    )
    assert result.exit_code == 0
    config = (tmp_path / "slurm" / "nextflow.config").read_text()
    assert "process.executor = 'slurm'" in config
    assert "process.queue = 'general'" in config
    assert "--account=lab" in config


def test_run_slurm_refuses_without_partition(tmp_path, monkeypatch):
    # A missing partition is refused by the preflight, not surfaced as a traceback.
    monkeypatch.setattr("contig.cli.default_executor", _fake_run_executor(TRACE_RUN_OK, GOOD_MQC))
    monkeypatch.setattr("contig.cli.shutil.which", lambda name: f"/usr/bin/{name}")
    result = runner.invoke(
        app,
        ["run", "--run-id", "slurmbad", "--runs-dir", str(tmp_path),
         "--backend", "slurm", "--opt", "account=lab"],
    )
    assert result.exit_code != 0
    assert "partition" in result.output.lower()


def test_run_slurm_refuses_when_sbatch_absent(tmp_path, monkeypatch):
    # PRD contract A: the slurm launch is refused BEFORE Nextflow runs when the
    # submission binaries are missing. Executor must never be touched.
    launched = {"n": 0}

    def spy(cmd, trace_path):
        launched["n"] += 1
        return 0

    monkeypatch.setattr("contig.cli.default_executor", spy)
    monkeypatch.setattr("contig.cli.shutil.which", lambda name: None)
    result = runner.invoke(
        app,
        ["run", "--run-id", "slurmnoslurm", "--runs-dir", str(tmp_path),
         "--backend", "slurm", "--queue", "general", "--opt", "account=lab"],
    )
    assert result.exit_code != 0
    assert "sbatch" in result.output.lower()
    assert launched["n"] == 0  # refused before any launch


def test_run_rejects_malformed_opt(tmp_path, monkeypatch):
    # An --opt without a key=value form is rejected, never silently dropped.
    monkeypatch.setattr("contig.cli.default_executor", _fake_run_executor(TRACE_RUN_OK, GOOD_MQC))
    result = runner.invoke(
        app,
        ["run", "--run-id", "badopt", "--runs-dir", str(tmp_path),
         "--backend", "slurm", "--queue", "general", "--opt", "noequalshere"],
    )
    assert result.exit_code != 0
    assert "opt" in result.output.lower()


def test_run_rejects_opt_with_unsafe_value(tmp_path, monkeypatch):
    # A backend-option value reaching the generated config is validated: a leading
    # dash (could be read as a flag) or shell metacharacters are refused.
    monkeypatch.setattr("contig.cli.default_executor", _fake_run_executor(TRACE_RUN_OK, GOOD_MQC))
    result = runner.invoke(
        app,
        ["run", "--run-id", "badval", "--runs-dir", str(tmp_path),
         "--backend", "slurm", "--queue", "general", "--opt", "account=-rm -rf"],
    )
    assert result.exit_code != 0


SNAKE_STATS = (
    '{"total_runtime": 7.0, "rules": {"align": {"mean-runtime": 4.0}, "count": {"mean-runtime": 3.0}}}'
)


def _fake_snake_executor(stats_text):
    def execute(cmd, artifact_path):
        Path(artifact_path).write_text(stats_text)
        return 0
    return execute


def test_run_with_snakemake_engine_drives_snakemake(tmp_path, monkeypatch):
    # A user reaches the second engine by naming it + a Snakefile; the run flows
    # through capture and record exactly like a Nextflow run does.
    seen = {}

    def spy(cmd, artifact_path):
        seen["cmd"] = cmd
        Path(artifact_path).write_text(SNAKE_STATS)
        return 0

    monkeypatch.setattr("contig.cli.default_executor", spy)
    snakefile = tmp_path / "Snakefile"
    snakefile.write_text("rule all:\n    input: []\n")
    result = runner.invoke(
        app,
        ["run", "--run-id", "snk", "--runs-dir", str(tmp_path),
         "--engine", "snakemake", "--snakefile", str(snakefile)],
    )
    assert result.exit_code == 0
    assert seen["cmd"][0] == "snakemake"
    record = load_bundle(tmp_path / "snk")
    assert {e.process for e in record.events} == {"align", "count"}


def test_run_snakemake_requires_a_snakefile(tmp_path, monkeypatch):
    monkeypatch.setattr("contig.cli.default_executor", _fake_snake_executor(SNAKE_STATS))
    result = runner.invoke(
        app,
        ["run", "--run-id", "snknofile", "--runs-dir", str(tmp_path), "--engine", "snakemake"],
    )
    assert result.exit_code != 0
    assert "snakefile" in result.output.lower()


def test_run_snakemake_rejects_missing_snakefile_path(tmp_path, monkeypatch):
    monkeypatch.setattr("contig.cli.default_executor", _fake_snake_executor(SNAKE_STATS))
    result = runner.invoke(
        app,
        ["run", "--run-id", "snkbad", "--runs-dir", str(tmp_path),
         "--engine", "snakemake", "--snakefile", str(tmp_path / "does_not_exist.smk")],
    )
    assert result.exit_code != 0
    assert "snakefile" in result.output.lower()


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


def test_run_writes_launch_manifest_for_test_profile(tmp_path, monkeypatch):
    # The reproduce sidecar must capture a test-profile invocation (no input).
    import json

    monkeypatch.setattr("contig.cli.default_executor", _fake_run_executor(TRACE_OK, GOOD_MQC))
    runner.invoke(app, ["run", "--run-id", "lm", "--runs-dir", str(tmp_path)])
    manifest = json.loads((tmp_path / "lm" / "launch.json").read_text())
    assert manifest["run_id"] == "lm"
    assert manifest["pipeline"] == "nf-core/rnaseq"
    assert manifest["input"] is None
    assert manifest["is_test_profile"] is True
    assert manifest["max_attempts"] == 3
    assert manifest["created_at"]
    # outdir/work_dir are re-defaulted on reproduce, never stored
    assert "outdir" not in manifest and "work_dir" not in manifest


def test_run_writes_launch_manifest_for_real_data(tmp_path, monkeypatch):
    import json

    sheet = _make_sheet(tmp_path)
    monkeypatch.setattr("contig.cli.default_executor", _fake_run_executor(TRACE_RUN_OK, GOOD_MQC))
    runner.invoke(
        app,
        ["run", "--run-id", "lmr", "--runs-dir", str(tmp_path / "runs"),
         "--input", str(sheet), "--genome", "GRCh38",
         "--max-memory", "6.GB", "--max-cpus", "2"],
    )
    manifest = json.loads((tmp_path / "runs" / "lmr" / "launch.json").read_text())
    assert manifest["input"] == str(sheet.resolve())
    assert manifest["genome"] == "GRCh38"
    assert manifest["max_memory"] == "6.GB"
    assert manifest["max_cpus"] == 2
    assert manifest["is_test_profile"] is False


def test_run_writes_launch_manifest_even_when_run_fails_early(tmp_path, monkeypatch):
    # The manifest is written BEFORE self_heal_run, so a failing run is still
    # reproducible.
    import json

    monkeypatch.setattr("contig.cli.default_executor", _fake_run_executor(TRACE_FAIL))
    runner.invoke(app, ["run", "--run-id", "lmf", "--runs-dir", str(tmp_path)])
    assert (tmp_path / "lmf" / "launch.json").exists()
    manifest = json.loads((tmp_path / "lmf" / "launch.json").read_text())
    assert manifest["run_id"] == "lmf"


def test_rerun_dispatches_identical_run_with_new_id(tmp_path, monkeypatch):
    # rerun reads launch.json from the original run and dispatches an identical
    # run under a fresh run id (matching pipeline/revision/profiles/caps).
    import json

    sheet = _make_sheet(tmp_path)
    monkeypatch.setattr("contig.cli.default_executor", _fake_run_executor(TRACE_RUN_OK, GOOD_MQC))
    runner.invoke(
        app,
        ["run", "--run-id", "orig", "--runs-dir", str(tmp_path / "runs"),
         "--input", str(sheet), "--genome", "GRCh38", "--max-cpus", "2"],
    )
    result = runner.invoke(
        app,
        ["rerun", "orig", "--runs-dir", str(tmp_path / "runs"), "--new-run-id", "copy"],
    )
    assert result.exit_code == 0
    assert "copy" in result.output
    new_manifest = json.loads((tmp_path / "runs" / "copy" / "launch.json").read_text())
    assert new_manifest["run_id"] == "copy"
    assert new_manifest["pipeline"] == "nf-core/rnaseq"
    assert new_manifest["genome"] == "GRCh38"
    assert new_manifest["max_cpus"] == 2
    assert new_manifest["input"] == str(sheet.resolve())
    # the new run produced its own bundle under its own id
    assert (tmp_path / "runs" / "copy" / "run_record.json").exists()


def test_rerun_generates_a_run_id_when_none_given(tmp_path, monkeypatch):
    monkeypatch.setattr("contig.cli.default_executor", _fake_run_executor(TRACE_OK, GOOD_MQC))
    runner.invoke(app, ["run", "--run-id", "orig2", "--runs-dir", str(tmp_path / "runs")])
    result = runner.invoke(app, ["rerun", "orig2", "--runs-dir", str(tmp_path / "runs")])
    assert result.exit_code == 0
    new_ids = [p.name for p in (tmp_path / "runs").iterdir() if p.is_dir() and p.name != "orig2"]
    assert len(new_ids) == 1
    assert new_ids[0] in result.output


def test_rerun_errors_when_launch_manifest_missing(tmp_path):
    result = runner.invoke(app, ["rerun", "ghost", "--runs-dir", str(tmp_path)])
    assert result.exit_code != 0
    assert "ghost" in result.output


def test_rerun_rejects_manifest_input_that_no_longer_exists(tmp_path, monkeypatch):
    # The manifest is not trusted blindly: if the recorded input path is gone,
    # rerun must refuse rather than launch against a missing sheet.
    sheet = _make_sheet(tmp_path)
    monkeypatch.setattr("contig.cli.default_executor", _fake_run_executor(TRACE_RUN_OK, GOOD_MQC))
    runner.invoke(
        app,
        ["run", "--run-id", "gone", "--runs-dir", str(tmp_path / "runs"),
         "--input", str(sheet), "--genome", "GRCh38"],
    )
    sheet.unlink()
    result = runner.invoke(app, ["rerun", "gone", "--runs-dir", str(tmp_path / "runs")])
    assert result.exit_code != 0


def _write_progress_dir(runs_dir, run_id, state, trace, repair=None):
    import json

    d = Path(runs_dir) / run_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "status.json").write_text(
        json.dumps({"run_id": run_id, "state": state,
                    "started_at": "2026-06-22T00:00:00+00:00",
                    "finished_at": None if state == "running" else "2026-06-22T00:00:30+00:00"})
    )
    (d / "trace.txt").write_text(trace)
    if repair is not None:
        (d / "repair_progress.jsonl").write_text(repair)
    return d


TRACE_MIXED = (
    "task_id\thash\tnative_id\tname\tstatus\texit\tsubmit\tduration\trealtime\n"
    "1\tab/cd\t1\tFASTQC (S1)\tCOMPLETED\t0\t-\t-\t-\n"
    "2\tef/gh\t2\tSTAR_ALIGN (S1)\tRUNNING\t-\t-\t-\t-\n"
)


def test_status_prints_completed_and_running_counts(tmp_path):
    _write_progress_dir(tmp_path, "s1", "running", TRACE_MIXED)
    result = runner.invoke(app, ["status", "s1", "--runs-dir", str(tmp_path)])
    assert result.exit_code == 0
    assert "running" in result.output.lower()
    assert "1" in result.output  # one completed
    assert "STAR_ALIGN (S1)" in result.output


def test_status_json_emits_machine_readable_snapshot(tmp_path):
    import json

    repair = json.dumps({
        "attempt": 1,
        "diagnosis": {"failure_class": "oom", "root_cause": "x", "evidence": [], "confidence": 0.9},
        "patch": None,
        "outcome": "patched_and_retried",
    }) + "\n"
    _write_progress_dir(tmp_path, "s2", "running", TRACE_MIXED, repair=repair)
    result = runner.invoke(app, ["status", "s2", "--runs-dir", str(tmp_path), "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["state"] == "running"
    assert data["tasks_completed"] == 1
    assert len(data["tasks_running"]) == 1
    assert data["repairs"][0]["failure_class"] == "oom"


def test_status_reports_missing_run_clearly(tmp_path):
    result = runner.invoke(app, ["status", "ghost", "--runs-dir", str(tmp_path)])
    assert result.exit_code != 0
    assert "missing" in result.output.lower() or "ghost" in result.output


def test_watch_returns_once_run_is_no_longer_running(tmp_path):
    # watch must exit promptly when the run has already finished (no sleeping on a
    # terminal state).
    _write_progress_dir(tmp_path, "w1", "finished", TRACE_MIXED)
    result = runner.invoke(app, ["watch", "w1", "--runs-dir", str(tmp_path), "--interval", "0"])
    assert result.exit_code == 0
    assert "finished" in result.output.lower()


def _write_status(runs_dir, run_id, state, pid=4321):
    import json

    d = Path(runs_dir) / run_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "status.json").write_text(
        json.dumps({"run_id": run_id, "state": state, "pid": pid,
                    "started_at": "2026-06-22T00:00:00+00:00", "finished_at": None})
    )
    return d


def test_cancel_writes_cancelled_state_for_running_run(tmp_path, monkeypatch):
    import json

    _write_status(tmp_path, "c1", "running")
    monkeypatch.setattr("contig.lifecycle.os.killpg", lambda pgid, sig: None)
    monkeypatch.setattr("contig.lifecycle.os.getpgid", lambda pid: pid)
    monkeypatch.setattr(
        "contig.lifecycle.os.kill",
        lambda pid, sig: (_ for _ in ()).throw(ProcessLookupError()),
    )
    result = runner.invoke(app, ["cancel", "c1", "--runs-dir", str(tmp_path)])
    assert result.exit_code == 0
    status = json.loads((tmp_path / "c1" / "status.json").read_text())
    assert status["state"] == "cancelled"


def test_cancel_refuses_a_finished_run_nonzero(tmp_path):
    _write_status(tmp_path, "c2", "finished")
    result = runner.invoke(app, ["cancel", "c2", "--runs-dir", str(tmp_path)])
    assert result.exit_code != 0
    assert "nothing to cancel" in result.output.lower()


def test_cancel_rejects_invalid_run_id(tmp_path):
    result = runner.invoke(app, ["cancel", "--", "-bad", "--runs-dir", str(tmp_path)])
    assert result.exit_code != 0


def test_resume_reruns_same_run_id_with_resume_flag(tmp_path, monkeypatch):
    import json

    # First a normal run writes launch.json, then we cancel it, then resume.
    monkeypatch.setattr("contig.cli.default_executor", _fake_run_executor(TRACE_RUN_OK, GOOD_MQC))
    runner.invoke(app, ["run", "--run-id", "rsm", "--runs-dir", str(tmp_path / "runs")])
    # mark it cancelled so it is resumable
    (tmp_path / "runs" / "rsm" / "status.json").write_text(
        json.dumps({"run_id": "rsm", "state": "cancelled", "pid": 4321,
                    "started_at": "2026-06-22T00:00:00+00:00", "finished_at": "2026-06-22T00:01:00+00:00"})
    )

    seen = {}

    def capture(cmd, trace_path):
        seen["cmd"] = cmd
        Path(trace_path).write_text(TRACE_RUN_OK)
        d = Path(trace_path).parent / "results" / "multiqc"
        d.mkdir(parents=True, exist_ok=True)
        (d / "multiqc_data.json").write_text(GOOD_MQC)
        return 0

    monkeypatch.setattr("contig.cli.default_executor", capture)
    result = runner.invoke(app, ["resume", "rsm", "--runs-dir", str(tmp_path / "runs")])
    assert result.exit_code == 0
    assert "-resume" in seen["cmd"]
    # the SAME run id is reused (not a fresh one)
    assert (tmp_path / "runs" / "rsm" / "run_record.json").exists()


def test_resume_refuses_a_finished_run(tmp_path, monkeypatch):
    import json

    monkeypatch.setattr("contig.cli.default_executor", _fake_run_executor(TRACE_RUN_OK, GOOD_MQC))
    runner.invoke(app, ["run", "--run-id", "fin", "--runs-dir", str(tmp_path / "runs")])
    result = runner.invoke(app, ["resume", "fin", "--runs-dir", str(tmp_path / "runs")])
    assert result.exit_code != 0
    assert "resumable" in result.output.lower()


def test_resume_errors_when_launch_manifest_missing(tmp_path):
    import json

    d = tmp_path / "noman"
    d.mkdir(parents=True)
    (d / "status.json").write_text(
        json.dumps({"run_id": "noman", "state": "cancelled", "pid": 1,
                    "started_at": "2026-06-22T00:00:00+00:00", "finished_at": None})
    )
    result = runner.invoke(app, ["resume", "noman", "--runs-dir", str(tmp_path)])
    assert result.exit_code != 0


def test_resume_rejects_invalid_run_id(tmp_path):
    result = runner.invoke(app, ["resume", "--", "-bad", "--runs-dir", str(tmp_path)])
    assert result.exit_code != 0


def test_approve_writes_approve_decision(tmp_path):
    import json

    _write_status(tmp_path, "ap", "awaiting_approval")
    result = runner.invoke(app, ["approve", "ap", "--runs-dir", str(tmp_path)])
    assert result.exit_code == 0
    data = json.loads((tmp_path / "ap" / "approval.json").read_text())
    assert data["decision"] == "approve"


def test_approve_reject_writes_reject_decision(tmp_path):
    import json

    _write_status(tmp_path, "rj", "awaiting_approval")
    result = runner.invoke(app, ["approve", "rj", "--reject", "--runs-dir", str(tmp_path)])
    assert result.exit_code == 0
    data = json.loads((tmp_path / "rj" / "approval.json").read_text())
    assert data["decision"] == "reject"


def test_approve_rejects_invalid_run_id(tmp_path):
    result = runner.invoke(app, ["approve", "--", "-bad", "--runs-dir", str(tmp_path)])
    assert result.exit_code != 0


def test_run_notify_forwards_webhook_and_emits_finished(tmp_path, monkeypatch):
    import json as _json

    from contig import notify

    posted = []
    monkeypatch.setattr(notify, "_post_webhook", lambda url, payload: posted.append(url))
    monkeypatch.setattr("contig.cli.default_executor", _fake_run_executor(TRACE_OK, GOOD_MQC))

    result = runner.invoke(
        app,
        ["run", "--run-id", "n1", "--runs-dir", str(tmp_path), "--notify", "https://hook.example/x"],
    )
    assert result.exit_code == 0
    feed = (tmp_path / "notifications.jsonl").read_text().splitlines()
    rows = [_json.loads(line) for line in feed]
    assert rows[-1]["kind"] == "finished"
    assert posted == ["https://hook.example/x"]


def test_run_rejects_notify_url_with_leading_dash(tmp_path, monkeypatch):
    monkeypatch.setattr("contig.cli.default_executor", _fake_run_executor(TRACE_OK, GOOD_MQC))
    result = runner.invoke(
        app,
        ["run", "--run-id", "n2", "--runs-dir", str(tmp_path), "--notify", "-bad"],
    )
    assert result.exit_code != 0


def test_run_rejects_non_http_notify_url(tmp_path, monkeypatch):
    monkeypatch.setattr("contig.cli.default_executor", _fake_run_executor(TRACE_OK, GOOD_MQC))
    result = runner.invoke(
        app,
        ["run", "--run-id", "n3", "--runs-dir", str(tmp_path), "--notify", "file:///etc/passwd"],
    )
    assert result.exit_code != 0


# --- contig verify (PRD contract B: output integrity) --------------------------
def _write_run_with_outputs(runs_dir, run_id, files):
    """Write a bundle whose results/ holds ``files`` and whose record records them."""
    from contig.bundle import compute_output_checksums

    run_dir = Path(runs_dir) / run_id
    results = run_dir / "results"
    results.mkdir(parents=True, exist_ok=True)
    for rel, content in files.items():
        path = results / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    record = RunRecord(
        run_id=run_id,
        pipeline="nf-core/rnaseq",
        pipeline_revision="3.26.0",
        target=ExecutionTarget(backend="local", container_runtime="docker", work_dir="w"),
        input_checksums={},
        events=[TaskEvent(process="X", status="COMPLETED", exit=0)],
        output_checksums=compute_output_checksums(results),
    )
    write_bundle(record, run_dir)
    return run_dir


def test_verify_passes_when_outputs_unchanged(tmp_path):
    _write_run_with_outputs(tmp_path, "ok", {"summary.txt": b"produced"})
    result = runner.invoke(app, ["verify", "ok", "--runs-dir", str(tmp_path)])
    assert result.exit_code == 0
    assert "verified" in result.output.lower()


def test_verify_detects_changed_output(tmp_path):
    run_dir = _write_run_with_outputs(tmp_path, "drift", {"summary.txt": b"produced"})
    (run_dir / "results" / "summary.txt").write_bytes(b"tampered")
    result = runner.invoke(app, ["verify", "drift", "--runs-dir", str(tmp_path)])
    assert result.exit_code != 0
    assert "summary.txt" in result.output


def test_verify_detects_missing_output(tmp_path):
    run_dir = _write_run_with_outputs(tmp_path, "gone", {"summary.txt": b"produced"})
    (run_dir / "results" / "summary.txt").unlink()
    result = runner.invoke(app, ["verify", "gone", "--runs-dir", str(tmp_path)])
    assert result.exit_code != 0
    assert "summary.txt" in result.output


def test_verify_nothing_to_verify_when_no_recorded_checksums(tmp_path):
    _write_run(tmp_path, "empty", [TaskEvent(process="X", status="COMPLETED", exit=0)])
    result = runner.invoke(app, ["verify", "empty", "--runs-dir", str(tmp_path)])
    assert result.exit_code == 0
    assert "nothing to verify" in result.output.lower()


def test_verify_json_reports_drift_shape(tmp_path):
    import json

    run_dir = _write_run_with_outputs(
        tmp_path, "j", {"a.txt": b"aaa", "sub/b.txt": b"bbb"}
    )
    (run_dir / "results" / "a.txt").write_bytes(b"changed")
    (run_dir / "results" / "sub" / "b.txt").unlink()
    result = runner.invoke(app, ["verify", "j", "--runs-dir", str(tmp_path), "--json"])
    assert result.exit_code != 0
    data = json.loads(result.output)
    assert data["ok"] is False
    assert data["changed"] == ["a.txt"]
    assert data["missing"] == ["sub/b.txt"]


def test_verify_json_ok_when_clean(tmp_path):
    import json

    _write_run_with_outputs(tmp_path, "clean", {"a.txt": b"aaa"})
    result = runner.invoke(app, ["verify", "clean", "--runs-dir", str(tmp_path), "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data == {"ok": True, "changed": [], "missing": []}


def test_keygen_prints_a_keypair(tmp_path):
    result = runner.invoke(app, ["keygen"])
    assert result.exit_code == 0
    # A hex private and public key are printed (64 hex chars each for Ed25519).
    import re
    hexes = re.findall(r"[0-9a-f]{64}", result.output)
    assert len(hexes) >= 2


def test_verify_reports_signature_ok_for_a_signed_run(tmp_path, monkeypatch):
    import json
    from contig import signing

    if not signing.signing_available():
        import pytest
        pytest.skip("cryptography not installed")
    priv, _pub = signing.generate_keypair()
    monkeypatch.setenv("CONTIG_SIGNING_KEY", priv)
    _write_run(tmp_path, "sgn", [TaskEvent(process="X", status="COMPLETED", exit=0)])
    result = runner.invoke(app, ["verify", "sgn", "--runs-dir", str(tmp_path), "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["signed"] is True and data["signature_ok"] is True


def test_verify_flags_a_tampered_signature(tmp_path, monkeypatch):
    import json
    from contig import signing

    if not signing.signing_available():
        import pytest
        pytest.skip("cryptography not installed")
    priv, _pub = signing.generate_keypair()
    monkeypatch.setenv("CONTIG_SIGNING_KEY", priv)
    _write_run(tmp_path, "tmp", [TaskEvent(process="X", status="COMPLETED", exit=0)])
    # Tamper the signed record on disk.
    rec_path = tmp_path / "tmp" / "run_record.json"
    rec = json.loads(rec_path.read_text())
    rec["pipeline"] = "nf-core/evil"
    rec_path.write_text(json.dumps(rec))
    result = runner.invoke(app, ["verify", "tmp", "--runs-dir", str(tmp_path), "--json"])
    data = json.loads(result.output)
    assert data["signed"] is True and data["signature_ok"] is False
    assert result.exit_code != 0


def test_verify_errors_on_missing_run(tmp_path):
    result = runner.invoke(app, ["verify", "nope", "--runs-dir", str(tmp_path)])
    assert result.exit_code != 0


def test_verify_rejects_invalid_run_id(tmp_path):
    result = runner.invoke(app, ["verify", "--", "-bad", "--runs-dir", str(tmp_path)])
    assert result.exit_code != 0


def test_run_auto_approve_applies_gated_patch(tmp_path, monkeypatch):
    # --auto-approve drives a needs_confirmation patch through without a human:
    # a missing-index failure is gated, then auto-approved, then succeeds.
    state = {"n": 0}

    def executor(cmd, trace_path):
        state["n"] += 1
        p = Path(trace_path)
        if state["n"] == 1:
            p.write_text(TRACE_FAIL)
            (p.parent / "run.log").write_text("ERROR: genome.fai index not found")
            return 1
        p.write_text(TRACE_RUN_OK)
        (p.parent / "results" / "multiqc").mkdir(parents=True, exist_ok=True)
        (p.parent / "results" / "multiqc" / "multiqc_data.json").write_text(GOOD_MQC)
        return 0

    monkeypatch.setattr("contig.cli.default_executor", executor)
    result = runner.invoke(
        app, ["run", "--run-id", "aa", "--runs-dir", str(tmp_path), "--auto-approve"]
    )
    assert result.exit_code == 0
    assert "approved_and_retried" in result.output


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


def test_eval_detector_json_emits_machine_readable_report(tmp_path):
    # The dashboard consumes this instead of re-implementing the detector.
    import json

    result = runner.invoke(app, ["eval-detector", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert "accuracy" in data and "per_class" in data and "mismatches" in data
    assert data["total"] >= 10


def test_eval_detector_scores_a_named_detector(tmp_path):
    import json

    result = runner.invoke(app, ["eval-detector", "--detector", "rules-strict", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert "accuracy" in data and "total" in data
    assert data["total"] >= 10


def test_eval_detector_rejects_an_unknown_detector(tmp_path):
    result = runner.invoke(app, ["eval-detector", "--detector", "nope"])
    assert result.exit_code != 0
    assert "rules" in result.output.lower()


def test_corpus_promote_moves_case_into_golden(tmp_path):
    from contig.corpus import load_corpus, save_corpus
    from contig.models import FailureCase, TaskEvent

    pending = tmp_path / "pending.jsonl"
    golden = tmp_path / "golden.jsonl"
    save_corpus(
        [FailureCase(case_id="r-1", description="d", source="pending:r",
                     events=[TaskEvent(process="X", status="FAILED", exit=1)],
                     log_text="boom", expected_class="tool_crash")],
        pending,
    )
    save_corpus([], golden)
    result = runner.invoke(
        app,
        ["corpus-promote", "r-1", "--pending", str(pending), "--golden", str(golden),
         "--label", "oom", "--history-file", str(tmp_path / "history.jsonl")],
    )
    assert result.exit_code == 0
    promoted = load_corpus(golden)
    assert len(promoted) == 1 and promoted[0].expected_class == "oom"
    assert load_corpus(pending) == []  # removed from pending


def test_eval_detector_snapshot_appends_to_history(tmp_path):
    from contig.eval_history import load_history

    history = tmp_path / "eval_history.jsonl"
    result = runner.invoke(
        app, ["eval-detector", "--snapshot", "--history-file", str(history)]
    )
    assert result.exit_code == 0
    snaps = load_history(history)
    assert len(snaps) == 1
    assert snaps[0].corpus_sha  # tied to a corpus version
    assert snaps[0].corpus_size >= 10


def test_eval_detector_snapshot_tags_the_detector_name(tmp_path):
    from contig.eval_history import load_history

    history = tmp_path / "eval_history.jsonl"
    result = runner.invoke(
        app,
        ["eval-detector", "--detector", "rules-strict", "--snapshot",
         "--history-file", str(history)],
    )
    assert result.exit_code == 0
    snaps = load_history(history)
    assert snaps[0].detector == "rules-strict"


def test_eval_detector_snapshot_defaults_detector_tag_to_rules(tmp_path):
    from contig.eval_history import load_history

    history = tmp_path / "eval_history.jsonl"
    result = runner.invoke(
        app, ["eval-detector", "--snapshot", "--history-file", str(history)]
    )
    assert result.exit_code == 0
    snaps = load_history(history)
    assert snaps[0].detector == "rules"


def test_eval_detector_history_prints_trend(tmp_path):
    from contig.eval_history import append_snapshot, snapshot_from_report
    from contig.models import ClassScore, DetectorEvalReport

    history = tmp_path / "eval_history.jsonl"
    report = DetectorEvalReport(total=2, correct=2, accuracy=1.0,
                                per_class={"oom": ClassScore(support=1, predicted=1, correct=1, precision=1.0, recall=1.0)})
    append_snapshot(snapshot_from_report(report, timestamp="2026-06-22T00:00:00+00:00",
                                         corpus_size=2, corpus_sha="abc", contig_version="0.0.1"), history)
    result = runner.invoke(app, ["eval-detector", "--history", "--history-file", str(history)])
    assert result.exit_code == 0
    assert "2026-06-22" in result.output
    assert "100" in result.output  # accuracy rendered


def test_eval_detector_history_json_emits_snapshots(tmp_path):
    import json

    from contig.eval_history import append_snapshot, snapshot_from_report
    from contig.models import DetectorEvalReport

    history = tmp_path / "eval_history.jsonl"
    report = DetectorEvalReport(total=1, correct=1, accuracy=1.0)
    append_snapshot(snapshot_from_report(report, timestamp="t", corpus_size=1,
                                         corpus_sha="abc", contig_version="0.0.1"), history)
    result = runner.invoke(app, ["eval-detector", "--history", "--json", "--history-file", str(history)])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert isinstance(data, list)
    assert data[0]["accuracy"] == 1.0
    assert data[0]["corpus_sha"] == "abc"


def test_corpus_promote_auto_appends_snapshot(tmp_path):
    from contig.corpus import save_corpus
    from contig.eval_history import load_history
    from contig.models import FailureCase, TaskEvent

    pending = tmp_path / "pending.jsonl"
    golden = tmp_path / "golden.jsonl"
    history = tmp_path / "eval_history.jsonl"
    save_corpus(
        [FailureCase(case_id="r-1", description="d", source="pending:r",
                     events=[TaskEvent(process="STAR", status="FAILED", exit=137)],
                     log_text="out of memory exit 137", expected_class="oom")],
        pending,
    )
    save_corpus([], golden)
    result = runner.invoke(
        app,
        ["corpus-promote", "r-1", "--pending", str(pending), "--golden", str(golden),
         "--history-file", str(history)],
    )
    assert result.exit_code == 0
    snaps = load_history(history)
    assert len(snaps) == 1  # a snapshot of the golden corpus was recorded on promote


def test_corpus_promote_unknown_case_errors(tmp_path):
    from contig.corpus import save_corpus

    pending = tmp_path / "pending.jsonl"
    save_corpus([], pending)
    result = runner.invoke(
        app, ["corpus-promote", "nope", "--pending", str(pending), "--golden", str(tmp_path / "g.jsonl")]
    )
    assert result.exit_code != 0


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


def test_plan_json_emits_machine_readable_plan(tmp_path):
    import json

    sheet = _make_sheet(tmp_path)
    result = runner.invoke(
        app,
        ["plan", "--goal", "find differentially expressed genes",
         "--input", str(sheet), "--genome", "GRCh38", "--json"],
    )
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["pipeline"] == "nf-core/rnaseq"
    assert "params" in data and "warnings" in data and "revision" in data


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


def _write_run_with_usage(runs_dir, run_id, usage):
    record = RunRecord(
        run_id=run_id,
        pipeline="nf-core/rnaseq",
        pipeline_revision="3.26.0",
        target=ExecutionTarget(backend="local", container_runtime="docker", work_dir="w"),
        input_checksums={},
        events=[TaskEvent(process="X", status="COMPLETED", exit=0)],
        resource_usage=usage,
    )
    write_bundle(record, Path(runs_dir) / run_id)


def test_cost_defaults_to_zero_on_local(tmp_path):
    _write_run_with_usage(
        tmp_path, "c1",
        [TaskResource(process="STAR", name="STAR", realtime_sec=3600.0, peak_rss_mb=1024.0, pct_cpu=100.0)],
    )
    result = runner.invoke(app, ["cost", "c1", "--runs-dir", str(tmp_path), "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["currency"] == "USD"
    assert payload["rate_cpu_hour"] == 0.0
    assert payload["total"] == 0.0
    assert payload["by_task"][0]["name"] == "STAR"


def test_cost_applies_cpu_hour_rate(tmp_path):
    _write_run_with_usage(
        tmp_path, "c2",
        [TaskResource(process="STAR", name="STAR", realtime_sec=3600.0, peak_rss_mb=0.0, pct_cpu=100.0)],
    )
    result = runner.invoke(
        app,
        ["cost", "c2", "--runs-dir", str(tmp_path), "--rate-cpu-hour=2.0", "--json"],
    )
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["total"] == 2.0


def test_cost_reports_zero_for_run_without_resource_usage(tmp_path):
    _write_run_with_usage(tmp_path, "c3", [])
    result = runner.invoke(
        app,
        ["cost", "c3", "--runs-dir", str(tmp_path), "--rate-cpu-hour=5.0", "--json"],
    )
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["total"] == 0.0
    assert payload["by_task"] == []


def test_cost_rejects_an_unsafe_run_id(tmp_path):
    result = runner.invoke(app, ["cost", "-badid", "--runs-dir", str(tmp_path)])
    assert result.exit_code != 0


def test_cost_reports_missing_run(tmp_path):
    result = runner.invoke(app, ["cost", "ghost", "--runs-dir", str(tmp_path)])
    assert result.exit_code != 0


def test_cost_text_output_shows_total_and_currency(tmp_path):
    _write_run_with_usage(
        tmp_path, "c4",
        [TaskResource(process="STAR", name="STAR", realtime_sec=3600.0, peak_rss_mb=0.0, pct_cpu=100.0)],
    )
    result = runner.invoke(
        app,
        ["cost", "c4", "--runs-dir", str(tmp_path), "--rate-cpu-hour=1.5", "--currency=EUR"],
    )
    assert result.exit_code == 0
    assert "EUR" in result.output
    assert "STAR" in result.output


def _estimate_sheet(tmp_path, n=2):
    lines = ["sample,fastq_1,fastq_2,strandedness"]
    for i in range(1, n + 1):
        (tmp_path / f"e{i}_R1.fastq.gz").write_bytes(b"\x1f\x8bR1")
        (tmp_path / f"e{i}_R2.fastq.gz").write_bytes(b"\x1f\x8bR2")
        lines.append(f"E{i},e{i}_R1.fastq.gz,e{i}_R2.fastq.gz,auto")
    sheet = tmp_path / "estimate_sheet.csv"
    sheet.write_text("\n".join(lines) + "\n")
    return sheet


def test_estimate_json_emits_pinned_shape(tmp_path):
    sheet = _estimate_sheet(tmp_path, 3)
    result = runner.invoke(
        app,
        ["estimate", "--pipeline", "nf-core/rnaseq", "--input", str(sheet),
         "--runs-dir", str(tmp_path), "--json"],
    )
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["basis"] == "heuristic"
    assert data["n_samples"] == 3
    assert data["pipeline"] == "nf-core/rnaseq"


def test_estimate_counts_samples_from_the_sheet(tmp_path):
    sheet = _estimate_sheet(tmp_path, 5)
    result = runner.invoke(
        app,
        ["estimate", "--pipeline", "nf-core/rnaseq", "--input", str(sheet),
         "--runs-dir", str(tmp_path), "--json"],
    )
    assert result.exit_code == 0
    assert json.loads(result.output)["n_samples"] == 5


def test_estimate_text_output_shows_runtime_and_cost(tmp_path):
    sheet = _estimate_sheet(tmp_path, 2)
    result = runner.invoke(
        app,
        ["estimate", "--pipeline", "nf-core/rnaseq", "--input", str(sheet),
         "--runs-dir", str(tmp_path), "--rate-cpu-hour=1.0", "--currency=EUR"],
    )
    assert result.exit_code == 0
    assert "EUR" in result.output


def test_estimate_rejects_a_missing_sheet(tmp_path):
    result = runner.invoke(
        app,
        ["estimate", "--pipeline", "nf-core/rnaseq",
         "--input", str(tmp_path / "nope.csv"), "--runs-dir", str(tmp_path)],
    )
    assert result.exit_code != 0


def test_estimate_rejects_an_unsafe_pipeline_value(tmp_path):
    sheet = _estimate_sheet(tmp_path, 2)
    result = runner.invoke(
        app,
        ["estimate", "--pipeline", "--evil", "--input", str(sheet),
         "--runs-dir", str(tmp_path)],
    )
    assert result.exit_code != 0


def _write_provenance_run(runs_dir, run_id):
    record = RunRecord(
        run_id=run_id,
        pipeline="nf-core/rnaseq",
        pipeline_revision="3.26.0",
        target=ExecutionTarget(backend="local", container_runtime="docker", work_dir="w"),
        input_checksums={"samplesheet.csv": "a" * 64},
        output_checksums={"multiqc/multiqc_report.html": "c" * 64},
        parameters={"genome": "GRCh38"},
        container_digests={"star": "sha256:deadbeef"},
        nextflow_version="24.10.0",
        events=[TaskEvent(process="STAR", status="COMPLETED", exit=0)],
        qc_results=[QCResult(check="mapping_rate", status="pass", message="ok", value=92.0)],
    )
    write_bundle(record, Path(runs_dir) / run_id)


def test_export_rocrate_prints_json_ld(tmp_path):
    _write_provenance_run(tmp_path, "p1")
    result = runner.invoke(app, ["export", "p1", "--rocrate", "--runs-dir", str(tmp_path)])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert "@graph" in data
    assert "@context" in data


def test_export_rocrate_writes_to_output_file(tmp_path):
    _write_provenance_run(tmp_path, "p1")
    out = tmp_path / "ro-crate-metadata.json"
    result = runner.invoke(
        app,
        ["export", "p1", "--rocrate", "--output", str(out), "--runs-dir", str(tmp_path)],
    )
    assert result.exit_code == 0
    data = json.loads(out.read_text())
    assert data["@graph"][0]["@id"] == "ro-crate-metadata.json"


def test_export_rejects_a_missing_run(tmp_path):
    result = runner.invoke(app, ["export", "ghost", "--rocrate", "--runs-dir", str(tmp_path)])
    assert result.exit_code != 0


def test_export_rejects_an_unsafe_run_id(tmp_path):
    result = runner.invoke(app, ["export", "../etc", "--rocrate", "--runs-dir", str(tmp_path)])
    assert result.exit_code != 0


def test_methods_prints_a_paragraph(tmp_path):
    _write_provenance_run(tmp_path, "p1")
    result = runner.invoke(app, ["methods", "p1", "--runs-dir", str(tmp_path)])
    assert result.exit_code == 0
    assert "nf-core/rnaseq" in result.output
    assert "3.26.0" in result.output


def test_methods_writes_to_output_file(tmp_path):
    _write_provenance_run(tmp_path, "p1")
    out = tmp_path / "methods.txt"
    result = runner.invoke(
        app, ["methods", "p1", "--output", str(out), "--runs-dir", str(tmp_path)]
    )
    assert result.exit_code == 0
    assert "nf-core/rnaseq" in out.read_text()


def test_methods_rejects_a_missing_run(tmp_path):
    result = runner.invoke(app, ["methods", "ghost", "--runs-dir", str(tmp_path)])
    assert result.exit_code != 0


def test_methods_rejects_an_unsafe_run_id(tmp_path):
    result = runner.invoke(app, ["methods", "../etc", "--runs-dir", str(tmp_path)])
    assert result.exit_code != 0
