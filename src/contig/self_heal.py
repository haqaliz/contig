"""The self-healing loop: Contig's core IP (ARCHITECTURE §5).

Wrap a run in a bounded, observable, fully-logged control loop:

    EXECUTE → DETECT → DIAGNOSE → PROPOSE → (apply safe patch) → re-run

Every detect→diagnose→patch→outcome transition is persisted to the RunRecord's
`repair_history`, so the repair chain is provenance. Only `safe` patches
auto-apply; `needs_confirmation`/`destructive` patches pause the loop. The loop
is bounded by `max_attempts`.
"""

from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from contig.bundle import compute_output_checksums, write_bundle
from contig.corpus import append_case, failure_case_from_run
from contig.detect import diagnose_failure
from contig.events import parse_resource_usage_file
from contig.models import ExecutionTarget, Patch, RepairStep, RunRecord, RunSummary
from contig.notify import emit_event
from contig.repair import propose_patches
from contig.runner import (
    Executor,
    PipelineExecutionError,
    default_executor,
    read_run_log,
    read_task_errors,
    run_pipeline,
)

_DEFAULT_MEMORY_GB = 8
_DEFAULT_TIME_HOURS = 4

# A diagnosis below this confidence is treated as ambiguous: even a single gated
# fix is offered as a choice rather than a take-it-or-leave-it confirm (contract D).
_AMBIGUOUS_CONFIDENCE = 0.5


def _write_status(run_dir: Path, state: str) -> None:
    """Write runs/<id>/status.json so a run is observable while in flight.

    run_record.json only appears at the end, so the dashboard reads this marker
    to tell "running" from "finished"/"error". started_at is preserved across
    updates; finished_at is set once the run leaves the running state.
    """
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    path = run_dir / "status.json"
    now = datetime.now(timezone.utc).isoformat()
    started_at = now
    if path.exists():
        try:
            started_at = json.loads(path.read_text()).get("started_at", now)
        except (ValueError, OSError):
            started_at = now
    path.write_text(
        json.dumps(
            {
                "run_id": run_dir.name,
                "state": state,
                "pid": os.getpid(),
                "started_at": started_at,
                "finished_at": None if state == "running" else now,
            }
        )
    )


def _record_attempt(
    run_dir: Path, repair_history: list[RepairStep], step: RepairStep
) -> None:
    """Append a resolved attempt to repair_history and to repair_progress.jsonl.

    The jsonl line is written the moment the attempt resolves so a live view can
    show attempts as they happen; it mirrors what later lands in repair_history
    (PRD contract B). The file stays absent until the first failure.
    """
    repair_history.append(step)
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    with open(run_dir / "repair_progress.jsonl", "a") as fh:
        fh.write(step.model_dump_json() + "\n")


def _safe_patch(patches: list[Patch]) -> Patch | None:
    return next((p for p in patches if p.risk == "safe"), None)


def _gated_candidates(patches: list[Patch]) -> list[Patch]:
    """The non-safe (gated) patches, kept in their proposed best-first order."""
    return [p for p in patches if p.risk != "safe"]


def _is_ambiguous(diagnosis, gated: list[Patch]) -> bool:
    """True when the gated decision should be a CHOICE rather than a single confirm.

    Ambiguous (contract D) when the diagnosis confidence is below the threshold, OR
    when there is more than one viable non-safe candidate and no single safe fix.
    Reached only on the gated path (caller has already established no safe patch).
    """
    return diagnosis.confidence < _AMBIGUOUS_CONFIDENCE or len(gated) > 1


def _validated_choice(
    options: list[Patch], decision: object, choice: object
) -> Patch | None:
    """The chosen option iff the decision approves with a valid in-range index.

    A reject, a timeout (no decision), an approve with no choice, or an out-of-range
    index all return None: the choice is refused, never silently coerced (contract D).
    """
    if decision != "approve" or not isinstance(choice, int) or isinstance(choice, bool):
        return None
    if 0 <= choice < len(options):
        return options[choice]
    return None


def _choice_refusal_outcome(decision: object, choice: object, n_options: int) -> str:
    """Why a choice gate did not apply: rejected, timed out, or an invalid choice."""
    if decision == "reject":
        return "rejected_by_user"
    if decision == "approve":
        # Approved, but the choice was missing or out of range: not actionable.
        return "invalid_choice_rejected"
    return "approval_timed_out"


# A poll function blocks until an approval decision lands or the timeout elapses,
# returning the decision dict (`{"decision": "approve"|"reject", ...}`) or None on
# timeout. Injected in tests so they never sleep for real.
ApprovalPoll = Callable[[Path, float], "dict | None"]


def _write_pending_approval(
    run_dir: Path, run_id: str, attempt: int, diagnosis, patch: Patch, timeout_sec: float
) -> None:
    """Write pending_approval.json: the gated patch a human is being asked to decide.

    The dashboard reads this to render the Approve/Reject prompt (PRD contract C).
    """
    (run_dir / "pending_approval.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "attempt": attempt,
                "requested_at": datetime.now(timezone.utc).isoformat(),
                "timeout_sec": timeout_sec,
                "decision_kind": "single",
                "diagnosis": {
                    "failure_class": diagnosis.failure_class,
                    "root_cause": diagnosis.root_cause,
                    "confidence": diagnosis.confidence,
                },
                "patch": {
                    "kind": patch.kind,
                    "risk": patch.risk,
                    "rationale": patch.rationale,
                    "operation": patch.operation,
                    "expected_signal": patch.expected_signal,
                },
            }
        )
    )


def _write_pending_choice(
    run_dir: Path,
    run_id: str,
    attempt: int,
    diagnosis,
    options: list[Patch],
    timeout_sec: float,
) -> None:
    """Write pending_approval.json for an AMBIGUOUS gate: a ranked choice (contract D).

    Carries an `options` array (ranked best-first) and `decision_kind: "choice"`,
    ALONGSIDE the existing single-patch fields (the best option) for back-compat, so
    an older dashboard still renders something. The human picks an option index in
    approval.json; the loop validates it against the options length.
    """
    best = options[0]
    (run_dir / "pending_approval.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "attempt": attempt,
                "requested_at": datetime.now(timezone.utc).isoformat(),
                "timeout_sec": timeout_sec,
                "decision_kind": "choice",
                "diagnosis": {
                    "failure_class": diagnosis.failure_class,
                    "root_cause": diagnosis.root_cause,
                    "confidence": diagnosis.confidence,
                },
                "options": [
                    {
                        "index": index,
                        "kind": option.kind,
                        "risk": option.risk,
                        "rationale": option.rationale,
                        "expected_signal": option.expected_signal,
                    }
                    for index, option in enumerate(options)
                ],
                "patch": {
                    "kind": best.kind,
                    "risk": best.risk,
                    "rationale": best.rationale,
                    "operation": best.operation,
                    "expected_signal": best.expected_signal,
                },
            }
        )
    )


def _clear_pending_approval(run_dir: Path) -> None:
    path = run_dir / "pending_approval.json"
    if path.exists():
        path.unlink()


def _poll_approval_file(run_dir: Path, timeout_sec: float, interval: float = 1.0) -> dict | None:
    """Default poll: wait for approval.json up to timeout_sec, then give up.

    Reads `{decision, decided_at, by?}` once the file appears. A malformed file is
    treated as no decision yet (the human re-writes it).
    """
    path = run_dir / "approval.json"
    deadline = time.monotonic() + timeout_sec
    while True:
        if path.exists():
            try:
                return json.loads(path.read_text())
            except (ValueError, OSError):
                pass
        if time.monotonic() >= deadline:
            return None
        time.sleep(min(interval, max(0.0, deadline - time.monotonic())))


def _lead_number(value: object, default: int) -> float:
    """Leading numeric part of a Nextflow resource literal ('16.GB' -> 16.0)."""
    if value is None:
        return float(default)
    match = re.match(r"[\d.]+", str(value).strip())
    return float(match.group()) if match else float(default)


def apply_patch(
    target: ExecutionTarget, patch: Patch, params: dict[str, object] | None = None
) -> tuple[ExecutionTarget, dict[str, object]]:
    """Apply a patch to the run inputs, returning the updated (target, params).

    Bounded by kind (PRD contract C/D):

    - `resource`: bump `process.resourceLimits` (what modern nf-core honors; the
      old `--max_memory` params are ignored).
    - `param`: merge `set_param` (its concrete key/value swap) into the pipeline
      params so the corrected parameter reaches the re-run's command.
    - `reference`: merge `set_param` (the reference swap, e.g. igenomes_ignore)
      into the params. A reference patch WITHOUT set_param (a build_index /
      resolve_reference signal) is re-run only: the re-run itself is the fix.
    - `env`: merge the operation into the target's backend_options (string-coerced
      so it rides into the generated config / re-run target).
    - `code`/`retry`: change nothing. The re-run itself is the fix.
    """
    params = dict(params or {})
    if patch.kind == "resource":
        mult = patch.operation.get("multiply", {})
        limits = dict(target.resource_limits)
        if "memory" in mult:
            bumped = int(_lead_number(limits.get("memory"), _DEFAULT_MEMORY_GB) * int(mult["memory"]))
            limits["memory"] = f"{bumped}.GB"
        if "time" in mult:
            bumped = int(_lead_number(limits.get("time"), _DEFAULT_TIME_HOURS) * int(mult["time"]))
            limits["time"] = f"{bumped}.h"
        return target.model_copy(update={"resource_limits": limits}), params
    if patch.kind in ("param", "reference"):
        # set_param carries the concrete swap (a corrected param, or a reference
        # knob like igenomes_ignore) merged into params so it reaches the re-run.
        # A reference patch with no set_param stays re-run only (unchanged params).
        swap = patch.operation.get("set_param")
        if isinstance(swap, dict):
            params.update(swap)
        return target, params
    if patch.kind == "env":
        options = dict(target.backend_options)
        options.update({k: str(v) for k, v in patch.operation.items()})
        return target.model_copy(update={"backend_options": options}), params
    return target, params


def self_heal_run(
    *,
    pipeline: str,
    revision: str,
    profiles: list[str],
    target: ExecutionTarget,
    input_paths: list,
    runs_dir,
    run_id: str,
    executor: Executor = default_executor,
    params: dict[str, object] | None = None,
    nextflow_version: str | None = None,
    max_attempts: int = 3,
    assay: str = "rnaseq",
    pending_corpus: str | Path | None = None,
    resume: bool = False,
    auto_approve: bool = False,
    approval_timeout: float = 1800,
    poll: ApprovalPoll = _poll_approval_file,
    propose: Callable[..., list[Patch]] = propose_patches,
    notify_webhook: str | None = None,
) -> RunRecord:
    """Run a pipeline and auto-recover from recoverable failures, logging the chain.

    Every failed attempt is also stashed to a pending-review failure corpus
    (`pending_corpus`, default `<runs_dir>/pending_corpus.jsonl`) with the
    detector's diagnosis as a PROVISIONAL label, so the corpus grows from real
    runs. These are separate from the golden corpus until a human confirms them.
    """
    run_dir = (Path(runs_dir) / run_id).resolve()
    _write_status(run_dir, "running")
    pending_path = Path(pending_corpus) if pending_corpus else Path(runs_dir) / "pending_corpus.jsonl"
    current_params = dict(params or {})
    current_target = target
    repair_history: list[RepairStep] = []
    attempt = 1

    while True:
        try:
            record = run_pipeline(
                pipeline=pipeline,
                revision=revision,
                profiles=profiles,
                target=current_target,
                input_paths=input_paths,
                runs_dir=runs_dir,
                run_id=run_id,
                executor=executor,
                params=current_params or None,
                nextflow_version=nextflow_version,
                resume=resume or attempt > 1,
                assay=assay,
            )
            return _finalize(
                record, repair_history, run_dir,
                runs_dir=runs_dir, run_id=run_id, webhook=notify_webhook,
            )
        except PipelineExecutionError as exc:
            events = exc.record.events if exc.record else []
            log_text = read_run_log(run_dir) + "\n" + read_task_errors(run_dir)
            diagnosis = diagnose_failure(events, log_text)
            # Stash this failure for the corpus with the detector's diagnosis as a
            # provisional label (pending human confirmation). Capture needs a
            # record (events) to be faithful; a trace-less failure has nothing.
            if exc.record is not None:
                append_case(
                    failure_case_from_run(
                        exc.record,
                        log_text,
                        diagnosis.failure_class,
                        case_id=f"{run_id}-attempt{attempt}",
                        source=f"pending:{run_id}",
                    ),
                    pending_path,
                )
            patches = propose(diagnosis)
            safe = _safe_patch(patches)

            if safe is None:
                # No automatic fix. If there's no patch at all there is nothing
                # left to try; if there's a gated patch, pause for a human
                # (or apply it now under --auto-approve).
                if not patches:
                    _record_attempt(
                        run_dir,
                        repair_history,
                        RepairStep(attempt=attempt, diagnosis=diagnosis, patch=None, outcome="gave_up"),
                    )
                    return _finalize(
                        exc.record, repair_history, run_dir,
                        runs_dir=runs_dir, run_id=run_id, webhook=notify_webhook,
                    )

                candidates = _gated_candidates(patches)
                gated = candidates[0]
                if attempt >= max_attempts:
                    _record_attempt(
                        run_dir,
                        repair_history,
                        RepairStep(attempt=attempt, diagnosis=diagnosis, patch=gated, outcome="gave_up"),
                    )
                    return _finalize(
                        exc.record, repair_history, run_dir,
                        runs_dir=runs_dir, run_id=run_id, webhook=notify_webhook,
                    )

                # --auto-approve is non-interactive: it always takes the best-ranked
                # gated fix, so there is no choice to make even when ambiguous.
                if auto_approve:
                    current_target, current_params = apply_patch(current_target, gated, current_params)
                    _record_attempt(
                        run_dir,
                        repair_history,
                        RepairStep(attempt=attempt, diagnosis=diagnosis, patch=gated, outcome="approved_and_retried"),
                    )
                    attempt += 1
                    continue

                if _is_ambiguous(diagnosis, candidates):
                    # AMBIGUOUS: present the ranked options and let the human pick one
                    # (contract D). approval.json carries {decision, choice}.
                    _write_pending_choice(
                        run_dir, run_id, attempt, diagnosis, candidates, approval_timeout
                    )
                    _write_status(run_dir, "awaiting_approval")
                    emit_event(
                        runs_dir, run_id, "awaiting_approval",
                        f"Run {run_id} is paused for a choice among {len(candidates)} fixes.",
                        webhook=notify_webhook,
                    )
                    result = poll(run_dir, approval_timeout) or {}
                    _clear_pending_approval(run_dir)
                    decision = result.get("decision")
                    choice = result.get("choice")

                    chosen = _validated_choice(candidates, decision, choice)
                    if chosen is not None:
                        current_target, current_params = apply_patch(current_target, chosen, current_params)
                        _write_status(run_dir, "running")
                        _record_attempt(
                            run_dir,
                            repair_history,
                            RepairStep(attempt=attempt, diagnosis=diagnosis, patch=chosen, outcome="chose_and_retried"),
                        )
                        attempt += 1
                        continue

                    outcome = _choice_refusal_outcome(decision, choice, len(candidates))
                    _record_attempt(
                        run_dir,
                        repair_history,
                        RepairStep(attempt=attempt, diagnosis=diagnosis, patch=gated, outcome=outcome),
                    )
                    return _finalize(
                        exc.record, repair_history, run_dir,
                        runs_dir=runs_dir, run_id=run_id, webhook=notify_webhook,
                    )

                # The unambiguous single gated patch: a binary confirm gate.
                _write_pending_approval(
                    run_dir, run_id, attempt, diagnosis, gated, approval_timeout
                )
                _write_status(run_dir, "awaiting_approval")
                emit_event(
                    runs_dir, run_id, "awaiting_approval",
                    f"Run {run_id} is paused for approval on a {gated.kind} patch.",
                    webhook=notify_webhook,
                )
                result = poll(run_dir, approval_timeout)
                _clear_pending_approval(run_dir)
                decision = (result or {}).get("decision") if result else None

                if decision == "approve":
                    current_target, current_params = apply_patch(current_target, gated, current_params)
                    _write_status(run_dir, "running")
                    _record_attempt(
                        run_dir,
                        repair_history,
                        RepairStep(attempt=attempt, diagnosis=diagnosis, patch=gated, outcome="approved_and_retried"),
                    )
                    attempt += 1
                    continue

                outcome = "rejected_by_user" if decision == "reject" else "approval_timed_out"
                _record_attempt(
                    run_dir,
                    repair_history,
                    RepairStep(attempt=attempt, diagnosis=diagnosis, patch=gated, outcome=outcome),
                )
                return _finalize(
                    exc.record, repair_history, run_dir,
                    runs_dir=runs_dir, run_id=run_id, webhook=notify_webhook,
                )

            if attempt >= max_attempts:
                _record_attempt(
                    run_dir,
                    repair_history,
                    RepairStep(attempt=attempt, diagnosis=diagnosis, patch=safe, outcome="gave_up"),
                )
                return _finalize(
                    exc.record, repair_history, run_dir,
                    runs_dir=runs_dir, run_id=run_id, webhook=notify_webhook,
                )

            current_target, current_params = apply_patch(current_target, safe, current_params)
            _record_attempt(
                run_dir,
                repair_history,
                RepairStep(attempt=attempt, diagnosis=diagnosis, patch=safe, outcome="patched_and_retried"),
            )
            attempt += 1


def _finalize(
    record: RunRecord | None,
    repair_history: list[RepairStep],
    run_dir: Path,
    *,
    runs_dir,
    run_id: str,
    webhook: str | None = None,
) -> RunRecord:
    """Attach the repair history to the final record, persist it, and notify.

    Emits a terminal notification (PRD contract A): `finished` when the run's
    events show success, otherwise `failed` (a give-up, rejection, or timeout all
    finalize a failed record). A trace-less run produces no record and no
    terminal notification: there is nothing to report yet.
    """
    if record is None:
        # The run failed before producing any trace; nothing was captured.
        _write_status(run_dir, "error")
        raise PipelineExecutionError(1, None)
    record.repair_history = repair_history
    record.output_checksums = compute_output_checksums(_results_dir(record, run_dir))
    trace_path = Path(run_dir) / "trace.txt"
    if trace_path.exists():
        record.resource_usage = parse_resource_usage_file(trace_path)
    write_bundle(record, run_dir)
    _write_status(run_dir, "finished")
    succeeded = RunSummary.from_events(record.events).succeeded
    if succeeded:
        emit_event(runs_dir, run_id, "finished", f"Run {run_id} finished.", webhook=webhook)
    else:
        emit_event(runs_dir, run_id, "failed", f"Run {run_id} failed.", webhook=webhook)
    return record


def _results_dir(record: RunRecord, run_dir: Path) -> Path:
    """Where the run wrote its outputs: the pipeline outdir, else run_dir/results.

    The CLI absolutizes --outdir into record.parameters; a run launched without
    one (the test profile path) defaults to run_dir/results, mirroring the CLI.
    """
    outdir = record.parameters.get("outdir")
    return Path(str(outdir)) if outdir else Path(run_dir) / "results"
