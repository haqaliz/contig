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


def test_self_heal_populates_resource_usage_from_trace(tmp_path):
    # The final record carries per-task resource actuals parsed from trace.txt so
    # the dashboard and the cost model can price the run.
    trace = (
        "task_id\thash\tnative_id\tname\tstatus\texit\tsubmit\t"
        "duration\trealtime\t%cpu\tpeak_rss\n"
        "1\tab/cd\t1\tSTAR_ALIGN (S1)\tCOMPLETED\t0\t2026-01-01\t"
        "2m 5s\t2m 3s\t180.4%\t1.2 GB\n"
    )

    def executor(cmd, trace_path):
        _write(trace_path, trace, "done")
        return 0

    record = _heal(tmp_path, executor)
    assert len(record.resource_usage) == 1
    task = record.resource_usage[0]
    assert task.process == "STAR_ALIGN (S1)"
    assert task.realtime_sec == 123.0
    assert task.peak_rss_mb == 1228.8
    assert task.pct_cpu == 180.4


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


def test_apply_patch_param_merges_set_param_into_params(tmp_path):
    patch = Patch(kind="param", operation={"set_param": {"aligner": "star_salmon"}},
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


def test_apply_patch_reference_build_index_is_rerun_only(tmp_path):
    patch = Patch(kind="reference", operation={"build_index": True},
                  rationale="x", risk="needs_confirmation", expected_signal="s")
    target, params = apply_patch(_t(), patch, {"input": "sheet.csv"})
    assert params == {"input": "sheet.csv"}  # unchanged: re-run is the fix
    assert target.resource_limits == {}


def test_apply_patch_reference_set_param_swaps_the_reference_param(tmp_path):
    # A reference patch carrying set_param swaps the reference into params (e.g.
    # point --genome at a resolved build) so the applied patch changes the re-run.
    patch = Patch(kind="reference", operation={"set_param": {"genome": "GRCh38"}},
                  rationale="x", risk="needs_confirmation", expected_signal="s")
    target, params = apply_patch(_t(), patch, {"input": "sheet.csv"})
    assert params["genome"] == "GRCh38"
    assert params["input"] == "sheet.csv"  # other params preserved
    assert target.resource_limits == {}  # target untouched


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


def test_self_heal_finalize_populates_output_checksums(tmp_path):
    # On a successful finalize, the produced outputs under results/ are hashed
    # into the record so a later `contig verify` can detect drift (contract B).
    from contig.bundle import compute_output_checksums

    def executor(cmd, trace_path):
        run_dir = Path(trace_path).parent
        results = run_dir / "results"
        results.mkdir(parents=True, exist_ok=True)
        (results / "summary.txt").write_bytes(b"produced")
        _write(trace_path, TRACE_OK, "done")
        return 0

    record = _heal(tmp_path, executor)
    run_dir = tmp_path / "runs" / "r"
    assert record.output_checksums == compute_output_checksums(run_dir / "results")
    assert record.output_checksums["summary.txt"]


def test_self_heal_output_checksums_empty_when_no_results(tmp_path):
    def executor(cmd, trace_path):
        _write(trace_path, TRACE_OK, "done")
        return 0

    record = _heal(tmp_path, executor)
    assert record.output_checksums == {}


def _notifications(tmp_path):
    path = tmp_path / "runs" / "notifications.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines()]


def test_self_heal_emits_finished_notification_on_success(tmp_path):
    def executor(cmd, trace_path):
        _write(trace_path, TRACE_OK, "done")
        return 0

    _heal(tmp_path, executor)
    kinds = [n["kind"] for n in _notifications(tmp_path)]
    assert kinds == ["finished"]
    assert _notifications(tmp_path)[0]["run_id"] == "r"


def test_self_heal_emits_failed_notification_on_give_up(tmp_path):
    def executor(cmd, trace_path):
        _write(trace_path, TRACE_TOOL, "Segmentation fault in some_tool")
        return 1

    _heal(tmp_path, executor)
    kinds = [n["kind"] for n in _notifications(tmp_path)]
    assert kinds[-1] == "failed"


def test_self_heal_emits_awaiting_approval_notification_when_paused(tmp_path):
    _heal(tmp_path, _index_executor(), poll=lambda run_dir, timeout_sec: None)
    kinds = [n["kind"] for n in _notifications(tmp_path)]
    assert "awaiting_approval" in kinds


def test_self_heal_forwards_webhook_to_emit(tmp_path, monkeypatch):
    from contig import notify

    captured = []
    monkeypatch.setattr(notify, "_post_webhook", lambda url, payload: captured.append(url))

    def executor(cmd, trace_path):
        _write(trace_path, TRACE_OK, "done")
        return 0

    _heal(tmp_path, executor, notify_webhook="https://hook.example/x")
    assert captured == ["https://hook.example/x"]


# --- applied patch reaches the re-run (deeper self-heal, contract D) -----------
# Proven through the injected executor on the REAL proposer path: it captures
# the retry command (params ride there as --key value) and the generated config
# (env/resource ride there), so an applied param/env/reference patch
# demonstrably changes the next run. Each test triggers a real failure class,
# the matching gated patch is auto-approved, and the retry is inspected.


def _failing_then_capturing(state, log_text, on_retry):
    def executor(cmd, trace_path):
        state["n"] += 1
        if state["n"] == 1:
            _write(trace_path, TRACE_TOOL, log_text)
            return 1
        on_retry(cmd, trace_path)
        _write(trace_path, TRACE_OK, "done")
        return 0
    return executor


def test_self_heal_applied_param_patch_reaches_the_rerun_command(tmp_path):
    # A bad_param failure proposes a param patch carrying a corrected value; once
    # approved, the corrected parameter must appear in the retry's command.
    state = {"n": 0}
    seen = {}
    log = (
        "ERROR ~ Validation of pipeline parameters failed!\n"
        "The following invalid input values have been detected:\n"
        "* --aligner is not a valid parameter"
    )
    executor = _failing_then_capturing(
        state, log, lambda cmd, tp: seen.__setitem__("cmd", cmd)
    )
    record = _heal(tmp_path, executor, auto_approve=True, params={"input": "sheet.csv"})
    assert RunSummary.from_events(record.events).succeeded is True
    assert record.repair_history[0].diagnosis.failure_class == "bad_param"
    assert record.repair_history[0].patch.kind == "param"
    # the param patch reached the retry command (a real --key value pair)
    assert "--validate_params" in seen["cmd"]
    assert "False" in seen["cmd"]


def test_self_heal_applied_reference_patch_reaches_the_rerun_command(tmp_path):
    # A missing_reference failure proposes a reference patch that disables igenomes
    # so a local reference is used; the swapped param must reach the retry command.
    state = {"n": 0}
    seen = {}
    log = "Error: No such file or directory: /data/genome.fasta"
    executor = _failing_then_capturing(
        state, log, lambda cmd, tp: seen.__setitem__("cmd", cmd)
    )
    record = _heal(tmp_path, executor, auto_approve=True, params={"input": "sheet.csv"})
    assert RunSummary.from_events(record.events).succeeded is True
    assert record.repair_history[0].diagnosis.failure_class == "missing_reference"
    assert record.repair_history[0].patch.kind == "reference"
    assert "--igenomes_ignore" in seen["cmd"]
    assert "True" in seen["cmd"]


def test_self_heal_applied_env_patch_reaches_the_rerun_target(tmp_path):
    # A conda_solve_failed failure proposes an env patch; the env knob must land
    # on the target that the retry runs against (it rides backend_options into the
    # generated config). The final record carries the patched target, proving the
    # applied env change reached the re-run.
    state = {"n": 0}
    log = "ResolvePackageNotFound:\n  - bioconductor-dupradar=1.38"
    executor = _failing_then_capturing(state, log, lambda cmd, tp: None)
    record = _heal(tmp_path, executor, auto_approve=True, params={"input": "sheet.csv"})
    assert RunSummary.from_events(record.events).succeeded is True
    assert record.repair_history[0].diagnosis.failure_class == "conda_solve_failed"
    assert record.repair_history[0].patch.kind == "env"
    assert record.target.backend_options.get("relax_or_pin_env") == "True"


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


# --- guided escalation (PRD contract D) ----------------------------------------
# When a self-heal decision is AMBIGUOUS (low-confidence diagnosis, or several
# viable non-safe fixes and no single safe one), the gate becomes a CHOICE: the
# pending request carries a ranked `options` array (decision_kind "choice"), and
# the human picks one via approval.json's `choice` index. The existing single
# gated-patch path (decision_kind "single") is unchanged.


from contig.models import Diagnosis  # noqa: E402
from contig.self_heal import _is_ambiguous  # noqa: E402


def _gated(kind, op, rationale, signal):
    return Patch(
        kind=kind, operation=op, rationale=rationale,
        risk="needs_confirmation", expected_signal=signal,
    )


def _two_candidates(diagnosis):
    # Two viable non-safe fixes and no safe one: an ambiguous choice.
    return [
        _gated("reference", {"set_param": {"igenomes_ignore": True}},
               "Ignore igenomes and use the local reference.", "reference resolved"),
        _gated("reference", {"build_index": True},
               "Build the missing index before re-running.", "index present"),
    ]


def test_is_ambiguous_flags_low_confidence_single_gated_patch():
    # A single gated patch is normally the single path, but a low-confidence
    # diagnosis makes even that ambiguous: present it as a choice.
    diagnosis = Diagnosis(failure_class="missing_index", root_cause="guess", confidence=0.3)
    one = [_gated("reference", {"build_index": True}, "build it", "index present")]
    assert _is_ambiguous(diagnosis, one) is True


def test_is_ambiguous_flags_multiple_viable_non_safe_patches():
    diagnosis = Diagnosis(failure_class="missing_index", root_cause="sure", confidence=0.9)
    assert _is_ambiguous(diagnosis, _two_candidates(diagnosis)) is True


def test_is_ambiguous_clears_single_confident_gated_patch():
    diagnosis = Diagnosis(failure_class="missing_index", root_cause="sure", confidence=0.9)
    one = [_gated("reference", {"build_index": True}, "build it", "index present")]
    assert _is_ambiguous(diagnosis, one) is False


def test_self_heal_ambiguous_decision_writes_options_with_choice_kind(tmp_path):
    captured = {}

    def poll(run_dir, timeout_sec):
        captured["pending"] = json.loads((Path(run_dir) / "pending_approval.json").read_text())
        return None  # time out so the run stops after we inspect the request

    _heal(tmp_path, _index_executor(), poll=poll, propose=_two_candidates)
    pending = captured["pending"]
    assert pending["decision_kind"] == "choice"
    options = pending["options"]
    assert [o["index"] for o in options] == [0, 1]
    first = options[0]
    assert set(first) == {"index", "kind", "risk", "rationale", "expected_signal"}
    assert first["kind"] == "reference"
    assert first["risk"] == "needs_confirmation"
    # back-compat: the single-patch fields still describe the best option
    assert pending["patch"]["kind"] == options[0]["kind"]


def test_self_heal_single_gated_patch_keeps_single_decision_kind(tmp_path):
    captured = {}

    def poll(run_dir, timeout_sec):
        captured["pending"] = json.loads((Path(run_dir) / "pending_approval.json").read_text())
        return None

    _heal(tmp_path, _index_executor(), poll=poll)
    pending = captured["pending"]
    assert pending["decision_kind"] == "single"
    assert "options" not in pending


def test_self_heal_chosen_option_is_applied_and_reaches_the_rerun(tmp_path):
    # Pick option index 1 (build_index). The chosen option is applied and the loop
    # re-runs to success, recording the chose_and_retried outcome.
    state = {"n": 0}

    def executor(cmd, trace_path):
        state["n"] += 1
        if state["n"] == 1:
            _write(trace_path, TRACE_INDEX, "ERROR: genome.fai index not found")
            return 1
        _write(trace_path, TRACE_OK, "done")
        return 0

    def poll(run_dir, timeout_sec):
        return {"decision": "approve", "choice": 1, "decided_at": "2026-06-22T00:00:00+00:00"}

    record = _heal(tmp_path, executor, poll=poll, propose=_two_candidates)
    assert RunSummary.from_events(record.events).succeeded is True
    step = record.repair_history[0]
    assert step.outcome == "chose_and_retried"
    # the applied patch is the chosen option, not the best-ranked default
    assert step.patch.operation == {"build_index": True}
    assert not (tmp_path / "runs" / "r" / "pending_approval.json").exists()


def test_self_heal_out_of_range_choice_is_refused_not_applied(tmp_path):
    def poll(run_dir, timeout_sec):
        return {"decision": "approve", "choice": 9, "decided_at": "2026-06-22T00:00:00+00:00"}

    record = _heal(tmp_path, _index_executor(), poll=poll, propose=_two_candidates)
    assert RunSummary.from_events(record.events).succeeded is False
    assert record.repair_history[-1].outcome == "invalid_choice_rejected"
    assert not (tmp_path / "runs" / "r" / "pending_approval.json").exists()


def test_self_heal_choice_reject_stops_without_applying(tmp_path):
    def poll(run_dir, timeout_sec):
        return {"decision": "reject", "decided_at": "2026-06-22T00:00:00+00:00"}

    record = _heal(tmp_path, _index_executor(), poll=poll, propose=_two_candidates)
    assert record.repair_history[-1].outcome == "rejected_by_user"


def test_self_heal_choice_timeout_stops_without_applying(tmp_path):
    record = _heal(
        tmp_path, _index_executor(),
        poll=lambda run_dir, timeout_sec: None, propose=_two_candidates,
    )
    assert record.repair_history[-1].outcome == "approval_timed_out"


def test_self_heal_choice_missing_index_defaults_to_rejected(tmp_path):
    # Approve with no choice on a choice gate is not actionable: refuse it rather
    # than silently apply the best-ranked option.
    def poll(run_dir, timeout_sec):
        return {"decision": "approve", "decided_at": "2026-06-22T00:00:00+00:00"}

    record = _heal(tmp_path, _index_executor(), poll=poll, propose=_two_candidates)
    assert record.repair_history[-1].outcome == "invalid_choice_rejected"
    assert RunSummary.from_events(record.events).succeeded is False
