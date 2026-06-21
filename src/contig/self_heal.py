"""The self-healing loop: Contig's core IP (ARCHITECTURE §5).

Wrap a run in a bounded, observable, fully-logged control loop:

    EXECUTE → DETECT → DIAGNOSE → PROPOSE → (apply safe patch) → re-run

Every detect→diagnose→patch→outcome transition is persisted to the RunRecord's
`repair_history`, so the repair chain is provenance. Only `safe` patches
auto-apply; `needs_confirmation`/`destructive` patches pause the loop. The loop
is bounded by `max_attempts`.
"""

from __future__ import annotations

import re
from pathlib import Path

from contig.bundle import write_bundle
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
) -> RunRecord:
    """Run a pipeline and auto-recover from recoverable failures, logging the chain."""
    run_dir = (Path(runs_dir) / run_id).resolve()
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
            patches = propose_patches(diagnosis)
            safe = _safe_patch(patches)

            if safe is None:
                # No automatic fix: pause for a human if there's a gated patch,
                # otherwise we have nothing left to try.
                outcome = "stopped_for_confirmation" if patches else "gave_up"
                repair_history.append(
                    RepairStep(attempt=attempt, diagnosis=diagnosis, patch=patches[0] if patches else None, outcome=outcome)
                )
                return _finalize(exc.record, repair_history, run_dir)

            if attempt >= max_attempts:
                repair_history.append(
                    RepairStep(attempt=attempt, diagnosis=diagnosis, patch=safe, outcome="gave_up")
                )
                return _finalize(exc.record, repair_history, run_dir)

            current_target = apply_patch(current_target, safe)
            repair_history.append(
                RepairStep(attempt=attempt, diagnosis=diagnosis, patch=safe, outcome="patched_and_retried")
            )
            attempt += 1


def _finalize(record: RunRecord | None, repair_history: list[RepairStep], run_dir: Path) -> RunRecord:
    """Attach the repair history to the final record and persist the bundle."""
    if record is None:
        # The run failed before producing any trace; nothing was captured.
        raise PipelineExecutionError(1, None)
    record.repair_history = repair_history
    write_bundle(record, run_dir)
    return record
