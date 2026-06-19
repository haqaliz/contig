from pathlib import Path

from contig.bundle import load_bundle
from contig.models import ExecutionTarget
from contig.runner import build_nextflow_command, run_pipeline

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


def test_run_pipeline_invokes_executor_with_nextflow_command(tmp_path):
    seen = {}

    def capturing(cmd, trace_path):
        seen["cmd"] = cmd
        Path(trace_path).write_text(TRACE_2_OK)
        return 0

    _run(tmp_path, TRACE_2_OK, executor=capturing)
    assert seen["cmd"][:3] == ["nextflow", "run", "nf-core/rnaseq"]
    assert "-with-trace" in seen["cmd"]
