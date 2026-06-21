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
from datetime import datetime, timezone
from pathlib import Path

from contig.bundle import write_bundle
from contig.corpus import append_case, failure_case_from_run
from contig.detect import diagnose_failure
from contig.models import ExecutionTarget, Patch, RepairStep, RunRecord
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


def _lead_number(value: object, default: int) -> float:
    """Leading numeric part of a Nextflow resource literal ('16.GB' -> 16.0)."""
    if value is None:
        return float(default)
    match = re.match(r"[\d.]+", str(value).strip())
    return float(match.group()) if match else float(default)


def apply_patch(target: ExecutionTarget, patch: Patch) -> ExecutionTarget:
    """Return a new target with the patch's resource bump applied to resourceLimits.

    Resource bumps ride in Nextflow's `process.resourceLimits` (what modern
    nf-core honors; the old `--max_memory` params are ignored); a retry/other
    patch changes nothing (the re-run itself is the fix).
    """
    if patch.kind != "resource":
        return target
    mult = patch.operation.get("multiply", {})
    limits = dict(target.resource_limits)
    if "memory" in mult:
        bumped = int(_lead_number(limits.get("memory"), _DEFAULT_MEMORY_GB) * int(mult["memory"]))
        limits["memory"] = f"{bumped}.GB"
    if "time" in mult:
        bumped = int(_lead_number(limits.get("time"), _DEFAULT_TIME_HOURS) * int(mult["time"]))
        limits["time"] = f"{bumped}.h"
    return target.model_copy(update={"resource_limits": limits})


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
                resume=attempt > 1,
                assay=assay,
            )
            return _finalize(record, repair_history, run_dir)
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
            patches = propose_patches(diagnosis)
            safe = _safe_patch(patches)

            if safe is None:
                # No automatic fix: pause for a human if there's a gated patch,
                # otherwise we have nothing left to try.
                outcome = "stopped_for_confirmation" if patches else "gave_up"
                _record_attempt(
                    run_dir,
                    repair_history,
                    RepairStep(attempt=attempt, diagnosis=diagnosis, patch=patches[0] if patches else None, outcome=outcome),
                )
                return _finalize(exc.record, repair_history, run_dir)

            if attempt >= max_attempts:
                _record_attempt(
                    run_dir,
                    repair_history,
                    RepairStep(attempt=attempt, diagnosis=diagnosis, patch=safe, outcome="gave_up"),
                )
                return _finalize(exc.record, repair_history, run_dir)

            current_target = apply_patch(current_target, safe)
            _record_attempt(
                run_dir,
                repair_history,
                RepairStep(attempt=attempt, diagnosis=diagnosis, patch=safe, outcome="patched_and_retried"),
            )
            attempt += 1


def _finalize(record: RunRecord | None, repair_history: list[RepairStep], run_dir: Path) -> RunRecord:
    """Attach the repair history to the final record and persist the bundle."""
    if record is None:
        # The run failed before producing any trace; nothing was captured.
        _write_status(run_dir, "error")
        raise PipelineExecutionError(1, None)
    record.repair_history = repair_history
    write_bundle(record, run_dir)
    _write_status(run_dir, "finished")
    return record
