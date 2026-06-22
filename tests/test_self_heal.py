import json
from pathlib import Path

import pytest

from contig.corpus import load_corpus
from contig.models import ExecutionTarget, Patch, RunSummary
from contig.runner import PipelineExecutionError
from contig.self_heal import apply_patch, self_heal_run


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


def test_self_heal_pauses_for_approval_on_needs_confirmation(tmp_path):
    # A needs_confirmation patch no longer stops outright: the loop pauses and
    # awaits a human decision (contract C). With an immediate timeout poll it
    # records approval_timed_out.
    def executor(cmd, trace_path):
        _write(trace_path, TRACE_TOOL, "ERROR: genome.fai index not found")
        return 1

    record = _heal(tmp_path, executor, poll=lambda run_dir, timeout_sec: None)
    assert record.repair_history[0].diagnosis.failure_class == "missing_index"
    assert record.repair_history[0].outcome == "approval_timed_out"


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


def _t():
    return ExecutionTarget(backend="local", container_runtime="docker", work_dir="w")


def test_apply_patch_resource_bump_updates_target_leaves_params(tmp_path):
    patch = Patch(kind="resource", operation={"multiply": {"memory": 2}},
                  rationale="x", risk="safe", expected_signal="s")
    target, params = apply_patch(_t(), patch, {"input": "sheet.csv"})
    assert target.resource_limits["memory"] == "16.GB"
    assert params == {"input": "sheet.csv"}


def test_apply_patch_param_merges_operation_into_params(tmp_path):
    patch = Patch(kind="param", operation={"aligner": "star_salmon"},
                  rationale="x", risk="needs_confirmation", expected_signal="s")
    target, params = apply_patch(_t(), patch, {"input": "sheet.csv"})
    assert params["aligner"] == "star_salmon"
    assert params["input"] == "sheet.csv"
    assert target.resource_limits == {}  # target untouched


def test_apply_patch_env_merges_operation_into_backend_options(tmp_path):
    patch = Patch(kind="env", operation={"relax_or_pin_env": True},
                  rationale="x", risk="needs_confirmation", expected_signal="s")
    target, params = apply_patch(_t(), patch, {})
    assert target.backend_options["relax_or_pin_env"] == "True"


def test_apply_patch_reference_is_rerun_only(tmp_path):
    patch = Patch(kind="reference", operation={"build_index": True},
                  rationale="x", risk="needs_confirmation", expected_signal="s")
    target, params = apply_patch(_t(), patch, {"input": "sheet.csv"})
    assert params == {"input": "sheet.csv"}  # unchanged: re-run is the fix
    assert target.resource_limits == {}


def test_self_heal_resume_passes_resume_on_first_execute(tmp_path):
    # With resume=True the FIRST execute must carry -resume (continue a cancelled
    # or interrupted run against its cached work dir), not just retries.
    seen = {}

    def executor(cmd, trace_path):
        seen["cmd"] = cmd
        _write(trace_path, TRACE_OK, "done")
        return 0

    _heal(tmp_path, executor, resume=True)
    assert "-resume" in seen["cmd"]


def test_self_heal_first_execute_has_no_resume_by_default(tmp_path):
    seen = {}

    def executor(cmd, trace_path):
        seen["cmd"] = cmd
        _write(trace_path, TRACE_OK, "done")
        return 0

    _heal(tmp_path, executor)
    assert "-resume" not in seen["cmd"]


TRACE_INDEX = _trace("FAILED", 1)  # paired with a missing-index log -> gated patch


def _index_executor():
    def executor(cmd, trace_path):
        _write(trace_path, TRACE_INDEX, "ERROR: genome.fai index not found")
        return 1
    return executor


def test_self_heal_writes_pending_approval_when_gated_patch_needed(tmp_path):
    # No safe patch, but a needs_confirmation patch exists: the loop pauses and
    # writes the approval request (read here from inside the poll, while paused,
    # since the file is cleared once a decision lands).
    captured = {}

    def poll(run_dir, timeout_sec):
        captured["pending"] = json.loads((Path(run_dir) / "pending_approval.json").read_text())
        return None  # time out

    _heal(tmp_path, _index_executor(), poll=poll)
    pending = captured["pending"]
    assert pending["run_id"] == "r"
    assert pending["attempt"] == 1
    assert pending["diagnosis"]["failure_class"] == "missing_index"
    assert pending["patch"]["kind"] == "reference"
    assert pending["patch"]["risk"] == "needs_confirmation"
    assert "requested_at" in pending and "timeout_sec" in pending


def test_self_heal_sets_awaiting_approval_state_while_paused(tmp_path):
    seen = {}

    def poll(run_dir, timeout_sec):
        seen["state"] = json.loads((Path(run_dir) / "status.json").read_text())["state"]
        return None

    _heal(tmp_path, _index_executor(), poll=poll)
    assert seen["state"] == "awaiting_approval"


def test_self_heal_approve_applies_patch_and_records_approved_outcome(tmp_path):
    state = {"n": 0}

    def executor(cmd, trace_path):
        state["n"] += 1
        if state["n"] == 1:
            _write(trace_path, TRACE_INDEX, "ERROR: genome.fai index not found")
            return 1
        _write(trace_path, TRACE_OK, "done")
        return 0

    def poll(run_dir, timeout_sec):
        return {"decision": "approve", "decided_at": "2026-06-22T00:00:00+00:00"}

    record = _heal(tmp_path, executor, poll=poll)
    assert RunSummary.from_events(record.events).succeeded is True
    assert record.repair_history[0].outcome == "approved_and_retried"
    # the pending file is cleared once decided
    assert not (tmp_path / "runs" / "r" / "pending_approval.json").exists()
    final = json.loads((tmp_path / "runs" / "r" / "status.json").read_text())
    assert final["state"] == "finished"


def test_self_heal_reject_records_rejected_and_stops(tmp_path):
    def poll(run_dir, timeout_sec):
        return {"decision": "reject", "decided_at": "2026-06-22T00:00:00+00:00"}

    record = _heal(tmp_path, _index_executor(), poll=poll)
    assert record.repair_history[-1].outcome == "rejected_by_user"
    assert not (tmp_path / "runs" / "r" / "pending_approval.json").exists()


def test_self_heal_timeout_records_timed_out_and_stops(tmp_path):
    def poll(run_dir, timeout_sec):
        return None  # no decision arrived within the window

    record = _heal(tmp_path, _index_executor(), poll=poll)
    assert record.repair_history[-1].outcome == "approval_timed_out"
    assert not (tmp_path / "runs" / "r" / "pending_approval.json").exists()


def test_self_heal_auto_approve_applies_gated_patch_without_pending(tmp_path):
    state = {"n": 0}

    def executor(cmd, trace_path):
        state["n"] += 1
        if state["n"] == 1:
            _write(trace_path, TRACE_INDEX, "ERROR: genome.fai index not found")
            return 1
        _write(trace_path, TRACE_OK, "done")
        return 0

    record = _heal(tmp_path, executor, auto_approve=True)
    assert record.repair_history[0].outcome == "approved_and_retried"
    # auto-approve never writes a pending request (non-interactive path)
    assert not (tmp_path / "runs" / "r" / "pending_approval.json").exists()


def test_self_heal_gives_up_when_no_patch_at_all(tmp_path):
    # An unrecoverable tool crash has no patch (safe or gated): still gave_up, no
    # pending request written.
    def executor(cmd, trace_path):
        _write(trace_path, TRACE_TOOL, "Segmentation fault in some_tool")
        return 1

    record = _heal(tmp_path, executor)
    assert record.repair_history[-1].outcome == "gave_up"
    assert not (tmp_path / "runs" / "r" / "pending_approval.json").exists()


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
