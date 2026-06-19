from pathlib import Path

import pytest

from contig.bundle import load_bundle
from contig.models import ExecutionTarget
from contig.runner import (
    PipelineExecutionError,
    build_nextflow_command,
    default_executor,
    read_run_log,
    run_pipeline,
)


def test_default_executor_tees_stdout_and_stderr_to_run_log(tmp_path):
    trace = tmp_path / "trace.txt"
    rc = default_executor(["sh", "-c", "echo to_out; echo to_err >&2"], trace)
    assert rc == 0
    log = (tmp_path / "run.log").read_text()
    assert "to_out" in log and "to_err" in log


def test_default_executor_returns_nonzero_exit(tmp_path):
    trace = tmp_path / "trace.txt"
    assert default_executor(["sh", "-c", "exit 3"], trace) == 3


def test_read_run_log_returns_text_when_present(tmp_path):
    (tmp_path / "run.log").write_text("boom: out of memory")
    assert "out of memory" in read_run_log(tmp_path)


def test_read_run_log_returns_empty_when_absent(tmp_path):
    assert read_run_log(tmp_path) == ""

TRACE_2_OK = (
    "task_id\thash\tnative_id\tname\tstatus\texit\tsubmit\tduration\trealtime\n"
    "1\tab/cd\t101\tNFCORE_RNASEQ:FASTQC (S1)\tCOMPLETED\t0\t-\t-\t-\n"
    "2\tef/gh\t102\tNFCORE_RNASEQ:STAR_ALIGN (S1)\tCOMPLETED\t0\t-\t-\t-\n"
)
TRACE_1_FAIL = (
    "task_id\thash\tnative_id\tname\tstatus\texit\tsubmit\tduration\trealtime\n"
    "1\tab/cd\t101\tNFCORE_RNASEQ:STAR_ALIGN (S1)\tFAILED\t137\t-\t-\t-\n"
)


def _fake_executor(trace_text):
    def execute(cmd, trace_path):
        Path(trace_path).write_text(trace_text)
        return 0
    return execute


GOOD_MQC_JSON = (
    '{"report_general_stats_data":[{'
    '"S1":{"uniquely_mapped_percent":92.0,"percent_assigned":85.0,"total_reads":1000000.0},'
    '"S2":{"uniquely_mapped_percent":90.0,"percent_assigned":84.0,"total_reads":1100000.0}}]}'
)
LOW_MQC_JSON = '{"report_general_stats_data":[{"S2":{"uniquely_mapped_percent":30.0}}]}'


def _executor_with_qc(trace_text, mqc_json):
    def execute(cmd, trace_path):
        Path(trace_path).write_text(trace_text)
        mqc_dir = Path(trace_path).parent / "results" / "multiqc"
        mqc_dir.mkdir(parents=True, exist_ok=True)
        (mqc_dir / "multiqc_data.json").write_text(mqc_json)
        return 0
    return execute


def _local_target(work_dir):
    return ExecutionTarget(backend="local", container_runtime="docker", work_dir=str(work_dir))


def _run(tmp_path, trace_text, **overrides):
    reads = tmp_path / "reads_R1.fastq.gz"
    reads.write_bytes(b"@read1\nACGT\n+\n!!!!\n")
    kwargs = dict(
        pipeline="nf-core/rnaseq",
        revision="3.14.0",
        profiles=["test", "docker"],
        target=_local_target(tmp_path / "work"),
        input_paths=[reads],
        runs_dir=tmp_path / "runs",
        run_id="run-001",
        executor=_fake_executor(trace_text),
    )
    kwargs.update(overrides)
    return run_pipeline(**kwargs)


def test_command_starts_with_nextflow_run_pipeline_and_revision():
    cmd = build_nextflow_command(
        pipeline="nf-core/rnaseq", revision="3.14.0", profiles=["test", "docker"], trace_path="trace.txt"
    )
    assert cmd[:5] == ["nextflow", "run", "nf-core/rnaseq", "-r", "3.14.0"]


def test_command_joins_profiles_with_comma():
    cmd = build_nextflow_command(
        pipeline="nf-core/rnaseq", revision="3.14.0", profiles=["test", "docker"], trace_path="trace.txt"
    )
    i = cmd.index("-profile")
    assert cmd[i + 1] == "test,docker"


def test_command_wires_trace_capture():
    cmd = build_nextflow_command(
        pipeline="nf-core/rnaseq", revision="3.14.0", profiles=["test"], trace_path="/runs/r1/trace.txt"
    )
    i = cmd.index("-with-trace")
    assert cmd[i + 1] == "/runs/r1/trace.txt"


def test_command_appends_params_as_double_dash_flags():
    cmd = build_nextflow_command(
        pipeline="nf-core/rnaseq",
        revision="3.14.0",
        profiles=["test"],
        trace_path="trace.txt",
        params={"aligner": "star_salmon"},
    )
    i = cmd.index("--aligner")
    assert cmd[i + 1] == "star_salmon"


def test_command_includes_resume_flag_when_requested():
    cmd = build_nextflow_command(
        pipeline="nf-core/rnaseq", revision="3.26.0", profiles=["test"], trace_path="t.txt", resume=True
    )
    assert "-resume" in cmd


def test_command_omits_resume_flag_by_default():
    cmd = build_nextflow_command(
        pipeline="nf-core/rnaseq", revision="3.26.0", profiles=["test"], trace_path="t.txt"
    )
    assert "-resume" not in cmd


def test_command_with_no_params_has_no_double_dash_flags():
    cmd = build_nextflow_command(
        pipeline="nf-core/rnaseq", revision="3.14.0", profiles=["test"], trace_path="trace.txt"
    )
    assert not any(tok.startswith("--") for tok in cmd)


def test_run_pipeline_captures_events_from_the_trace(tmp_path):
    record = _run(tmp_path, TRACE_2_OK)
    assert record.run_id == "run-001"
    assert record.pipeline == "nf-core/rnaseq"
    assert len(record.events) == 2


def test_run_pipeline_attaches_qc_and_verdict_passes_on_good_multiqc(tmp_path):
    record = _run(tmp_path, TRACE_2_OK, executor=_executor_with_qc(TRACE_2_OK, GOOD_MQC_JSON))
    assert record.qc_results
    assert record.verdict == "pass"


def test_run_pipeline_verdict_fails_on_low_qc_even_when_run_succeeds(tmp_path):
    record = _run(tmp_path, TRACE_2_OK, executor=_executor_with_qc(TRACE_2_OK, LOW_MQC_JSON))
    assert record.verdict == "fail"


def test_run_pipeline_runs_structural_checks_on_bam_outputs(tmp_path):
    def exec_with_bam(cmd, trace_path):
        Path(trace_path).write_text(TRACE_2_OK)
        out = Path(trace_path).parent / "results" / "star"
        out.mkdir(parents=True, exist_ok=True)
        (out / "S1.bam").write_bytes(b"BAMDATA")
        (out / "S1.bam.bai").write_bytes(b"IDX")
        return 0

    record = _run(tmp_path, TRACE_2_OK, executor=exec_with_bam)
    checks = [r.check for r in record.qc_results]
    assert any(c.startswith("output_present:S1.bam") for c in checks)


def test_run_pipeline_does_not_fail_unindexed_intermediate_bams(tmp_path):
    # An intermediate BAM with no index must NOT produce a spurious index_present:fail
    # that drags the verdict to fail.
    def exec_with_unindexed_bam(cmd, trace_path):
        Path(trace_path).write_text(TRACE_2_OK)
        out = Path(trace_path).parent / "work"
        out.mkdir(parents=True, exist_ok=True)
        (out / "intermediate.bam").write_bytes(b"BAMDATA")  # no .bai
        return 0

    record = _run(tmp_path, TRACE_2_OK, executor=exec_with_unindexed_bam)
    assert not any(c.check.startswith("index_present") for c in record.qc_results)


def test_run_pipeline_unverified_when_run_ok_but_no_multiqc_output(tmp_path):
    record = _run(tmp_path, TRACE_2_OK)  # default fake writes only the trace
    assert record.qc_results == []
    assert record.verdict == "unverified"


def test_run_pipeline_records_input_checksums(tmp_path):
    record = _run(tmp_path, TRACE_2_OK)
    digest = record.input_checksums["reads_R1.fastq.gz"]
    assert len(digest) == 64


def test_run_pipeline_writes_a_reproduce_bundle_that_round_trips(tmp_path):
    record = _run(tmp_path, TRACE_2_OK)
    loaded = load_bundle(tmp_path / "runs" / "run-001")
    assert loaded == record


def test_run_pipeline_verdict_reflects_failed_task_via_summary(tmp_path):
    record = _run(tmp_path, TRACE_1_FAIL)
    from contig.models import RunSummary

    assert RunSummary.from_events(record.events).succeeded is False
    assert record.verdict == "fail"


def test_run_pipeline_invokes_executor_with_nextflow_command(tmp_path):
    seen = {}

    def capturing(cmd, trace_path):
        seen["cmd"] = cmd
        Path(trace_path).write_text(TRACE_2_OK)
        return 0

    _run(tmp_path, TRACE_2_OK, executor=capturing)
    assert seen["cmd"][:3] == ["nextflow", "run", "nf-core/rnaseq"]
    assert "-with-trace" in seen["cmd"]


def test_run_pipeline_passes_absolute_trace_path_even_when_runs_dir_relative(tmp_path, monkeypatch):
    # Nextflow runs with cwd=run_dir; a relative -with-trace path would resolve
    # against that cwd and land nested, so run_pipeline must absolutize it.
    monkeypatch.chdir(tmp_path)
    seen = {}

    def capturing(cmd, trace_path):
        seen["trace_path"] = Path(trace_path)
        seen["cmd_trace"] = cmd[cmd.index("-with-trace") + 1]
        Path(trace_path).write_text(TRACE_2_OK)
        return 0

    reads = tmp_path / "reads_R1.fastq.gz"
    reads.write_bytes(b"x")
    run_pipeline(
        pipeline="nf-core/rnaseq",
        revision="3.26.0",
        profiles=["test", "docker"],
        target=ExecutionTarget(backend="local", container_runtime="docker", work_dir="w"),
        input_paths=[reads],
        runs_dir="runs",  # relative on purpose
        run_id="r1",
        executor=capturing,
    )
    assert seen["trace_path"].is_absolute()
    assert Path(seen["cmd_trace"]).is_absolute()


def test_run_pipeline_raises_clear_error_on_nonzero_exit(tmp_path):
    def failing(cmd, trace_path):
        return 1  # e.g. config parse failure — no trace written

    with pytest.raises(PipelineExecutionError) as exc:
        _run(tmp_path, TRACE_2_OK, executor=failing)
    assert "1" in str(exc.value)


def test_run_pipeline_error_carries_returncode(tmp_path):
    def failing(cmd, trace_path):
        return 137

    with pytest.raises(PipelineExecutionError) as exc:
        _run(tmp_path, TRACE_2_OK, executor=failing)
    assert exc.value.returncode == 137


def test_run_pipeline_captures_bundle_even_when_run_fails(tmp_path):
    # A partial run: the executor writes a trace (some tasks recorded) then reports
    # failure. The failure data is the moat — it must still be captured.
    def failing_with_trace(cmd, trace_path):
        Path(trace_path).write_text(TRACE_1_FAIL)
        return 1

    with pytest.raises(PipelineExecutionError):
        _run(tmp_path, TRACE_1_FAIL, executor=failing_with_trace)

    record = load_bundle(tmp_path / "runs" / "run-001")
    assert len(record.events) == 1
    assert record.events[0].is_failure is True


def test_run_pipeline_error_carries_captured_record(tmp_path):
    def failing_with_trace(cmd, trace_path):
        Path(trace_path).write_text(TRACE_1_FAIL)
        return 1

    with pytest.raises(PipelineExecutionError) as exc:
        _run(tmp_path, TRACE_1_FAIL, executor=failing_with_trace)
    assert exc.value.record is not None
    assert exc.value.record.run_id == "run-001"


def test_run_pipeline_error_has_no_record_when_no_trace_written(tmp_path):
    def failing_no_trace(cmd, trace_path):
        return 1  # crashed before producing any trace

    with pytest.raises(PipelineExecutionError) as exc:
        _run(tmp_path, TRACE_2_OK, executor=failing_no_trace)
    assert exc.value.record is None
