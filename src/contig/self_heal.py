"""The self-healing loop — Contig's core IP (ARCHITECTURE §5).

Wrap a run in a bounded, observable, fully-logged control loop:

    EXECUTE → DETECT → DIAGNOSE → PROPOSE → (apply safe patch) → re-run

Every detect→diagnose→patch→outcome transition is persisted to the RunRecord's
`repair_history`, so the repair chain is provenance. Only `safe` patches
auto-apply; `needs_confirmation`/`destructive` patches pause the loop. The loop
is bounded by `max_attempts`.
"""

from __future__ import annotations

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
    run_pipeline,
)

_DEFAULT_MEMORY_GB = 8
_DEFAULT_TIME_HOURS = 4


def _safe_patch(patches: list[Patch]) -> Patch | None:
    return next((p for p in patches if p.risk == "safe"), None)


def apply_patch(params: dict[str, object], patch: Patch) -> dict[str, object]:
    """Return a new params dict with the patch applied (nf-core resource params).

    Resource bumps map to nf-core's real `--max_memory` / `--max_time` knobs;
    a retry changes nothing (the re-run itself is the fix).
    """
    new = dict(params)
    mult = patch.operation.get("multiply", {}) if patch.kind == "resource" else {}
    if "memory" in mult:
        current = int(new.get("_memory_gb", _DEFAULT_MEMORY_GB))
        bumped = current * int(mult["memory"])
        new["_memory_gb"] = bumped
        new["max_memory"] = f"{bumped}.GB"
    if "time" in mult:
        current = int(new.get("_time_h", _DEFAULT_TIME_HOURS))
        bumped = current * int(mult["time"])
        new["_time_h"] = bumped
        new["max_time"] = f"{bumped}.h"
    return new


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
    repair_history: list[RepairStep] = []
    attempt = 1

    while True:
        try:
            record = run_pipeline(
                pipeline=pipeline,
                revision=revision,
                profiles=profiles,
                target=target,
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
            diagnosis = diagnose_failure(events, read_run_log(run_dir))
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

            current_params = apply_patch(current_params, safe)
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
