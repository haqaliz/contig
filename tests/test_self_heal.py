import json
from pathlib import Path

import pytest

from contig.corpus import load_corpus
from contig.models import ExecutionTarget, RunSummary
from contig.runner import PipelineExecutionError
from contig.self_heal import self_heal_run


def _trace(status, exit_code):
    return (
        "task_id\thash\tnative_id\tname\tstatus\texit\tsubmit\tduration\trealtime\n"
        f"1\tab/cd\t1\tNFCORE_RNASEQ:STAR_ALIGN (S1)\t{status}\t{exit_code}\t-\t-\t-\n"
    )


TRACE_OK = _trace("COMPLETED", 0)
TRACE_OOM = _trace("FAILED", 137)
TRACE_TOOL = _trace("FAILED", 1)


def _write(trace_path, trace_text, log_text):
    Path(trace_path).write_text(trace_text)
    (Path(trace_path).parent / "run.log").write_text(log_text)


def _target(d):
    return ExecutionTarget(backend="local", container_runtime="docker", work_dir=str(d))


def _heal(tmp_path, executor, **over):
    kwargs = dict(
        pipeline="nf-core/rnaseq",
        revision="3.26.0",
        profiles=["test", "docker"],
        target=_target(tmp_path / "w"),
        input_paths=[],
        runs_dir=tmp_path / "runs",
        run_id="r",
        executor=executor,
        max_attempts=3,
    )
    kwargs.update(over)
    return self_heal_run(**kwargs)


def test_self_heal_recovers_from_oom_and_logs_repair(tmp_path):
    state = {"n": 0}

    def executor(cmd, trace_path):
        state["n"] += 1
        if state["n"] == 1:
            _write(trace_path, TRACE_OOM, "Process killed: out of memory (exit 137)")
            return 1
        _write(trace_path, TRACE_OK, "done")
        return 0

    record = _heal(tmp_path, executor)
    assert RunSummary.from_events(record.events).succeeded is True
    assert len(record.repair_history) == 1
    step = record.repair_history[0]
    assert step.diagnosis.failure_class == "oom"
    assert step.patch.risk == "safe"
    assert step.outcome == "patched_and_retried"


def test_self_heal_oom_bump_emits_bumped_resourcelimits(tmp_path):
    # The OOM fix must ride in the generated config's resourceLimits (what modern
    # nf-core honors), not the ignored --max_memory param. Default 8GB -> 16GB.
    state = {"n": 0, "retry_cfg": None}

    def executor(cmd, trace_path):
        state["n"] += 1
        if state["n"] == 1:
            _write(trace_path, TRACE_OOM, "out of memory exit 137")
            return 1
        state["retry_cfg"] = (Path(trace_path).parent / "nextflow.config").read_text()
        _write(trace_path, TRACE_OK, "done")
        return 0

    record = _heal(tmp_path, executor)
    assert RunSummary.from_events(record.events).succeeded is True
    assert "process.resourceLimits = [ memory: 16.GB ]" in state["retry_cfg"]


def test_self_heal_writes_status_running_then_finished(tmp_path):
    # The dashboard reads status.json to know a run is in flight (run_record.json
    # only appears at the end). It must say "running" during, "finished" after.
    seen = {}

    def executor(cmd, trace_path):
        sp = Path(trace_path).parent / "status.json"
        seen["during"] = json.loads(sp.read_text())["state"] if sp.exists() else None
        _write(trace_path, TRACE_OK, "ok")
        return 0

    _heal(tmp_path, executor)
    final = json.loads((tmp_path / "runs" / "r" / "status.json").read_text())
    assert seen["during"] == "running"
    assert final["state"] == "finished"


def test_self_heal_writes_status_error_when_no_record(tmp_path):
    # A run that produced no trace at all (engine could not even start) is "error",
    # not a stuck "running".
    def executor(cmd, trace_path):
        return 1  # nonzero, no trace written -> no record

    with pytest.raises(PipelineExecutionError):
        _heal(tmp_path, executor)
    final = json.loads((tmp_path / "runs" / "r" / "status.json").read_text())
    assert final["state"] == "error"


def test_self_heal_gives_up_on_unrecoverable_tool_crash(tmp_path):
    def executor(cmd, trace_path):
        _write(trace_path, TRACE_TOOL, "Segmentation fault in some_tool")
        return 1

    record = _heal(tmp_path, executor)
    assert RunSummary.from_events(record.events).succeeded is False
    assert record.verdict == "fail"
    assert record.repair_history[-1].outcome == "gave_up"


def test_self_heal_stashes_failure_as_pending_corpus_case(tmp_path):
    # Every failure is captured for the corpus with a PROVISIONAL label (the
    # detector's own guess) so a human can confirm it before it enters the
    # golden corpus. Stored separately, marked pending, so the eval never grades
    # the detector on its own guesses.
    def executor(cmd, trace_path):
        _write(trace_path, TRACE_TOOL, "Segmentation fault in some_tool")
        return 1

    _heal(tmp_path, executor)
    pending = load_corpus(tmp_path / "runs" / "pending_corpus.jsonl")
    assert len(pending) == 1
    assert pending[0].expected_class == "tool_crash"  # provisional = detector guess
    assert pending[0].source.startswith("pending:")
    assert pending[0].log_text  # the captured log travels with the case


def test_self_heal_does_not_stash_on_success(tmp_path):
    def executor(cmd, trace_path):
        _write(trace_path, TRACE_OK, "done")
        return 0

    _heal(tmp_path, executor)
    assert not (tmp_path / "runs" / "pending_corpus.jsonl").exists()


def test_self_heal_stops_for_confirmation_on_needs_confirmation(tmp_path):
    def executor(cmd, trace_path):
        _write(trace_path, TRACE_TOOL, "ERROR: genome.fai index not found")
        return 1

    record = _heal(tmp_path, executor)
    assert record.repair_history[0].diagnosis.failure_class == "missing_index"
    assert record.repair_history[0].outcome == "stopped_for_confirmation"


def test_self_heal_appends_repair_progress_line_per_attempt(tmp_path):
    # Each resolved self-heal attempt is appended to repair_progress.jsonl the
    # moment it resolves, so a live view can show attempts as they happen.
    from contig.models import RepairStep

    state = {"n": 0}

    def executor(cmd, trace_path):
        state["n"] += 1
        if state["n"] == 1:
            _write(trace_path, TRACE_OOM, "out of memory exit 137")
            return 1
        _write(trace_path, TRACE_OK, "done")
        return 0

    record = _heal(tmp_path, executor)
    progress = (tmp_path / "runs" / "r" / "repair_progress.jsonl").read_text().splitlines()
    assert len(progress) == 1
    step = RepairStep.model_validate_json(progress[0])
    assert step.attempt == 1
    assert step.diagnosis.failure_class == "oom"
    assert step.outcome == "patched_and_retried"
    # the live lines mirror the final repair_history exactly
    assert [s.model_dump() for s in record.repair_history] == [step.model_dump()]


def test_self_heal_repair_progress_records_each_attempt_in_order(tmp_path):
    from contig.models import RepairStep

    def executor(cmd, trace_path):
        _write(trace_path, TRACE_OOM, "out of memory exit 137")
        return 1

    _heal(tmp_path, executor, max_attempts=3)
    lines = (tmp_path / "runs" / "r" / "repair_progress.jsonl").read_text().splitlines()
    attempts = [RepairStep.model_validate_json(line).attempt for line in lines]
    assert attempts == sorted(attempts)
    assert attempts == [1, 2, 3]


def test_self_heal_writes_no_repair_progress_on_clean_run(tmp_path):
    def executor(cmd, trace_path):
        _write(trace_path, TRACE_OK, "done")
        return 0

    _heal(tmp_path, executor)
    assert not (tmp_path / "runs" / "r" / "repair_progress.jsonl").exists()


def test_self_heal_respects_max_attempts(tmp_path):
    attempts = {"n": 0}

    def executor(cmd, trace_path):
        attempts["n"] += 1
        _write(trace_path, TRACE_OOM, "out of memory exit 137")
        return 1

    record = _heal(tmp_path, executor, max_attempts=2)
    assert RunSummary.from_events(record.events).succeeded is False
    assert attempts["n"] <= 2
    assert len(record.repair_history) <= 2
