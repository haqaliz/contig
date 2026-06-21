"""A live snapshot of a run in flight (PRD dispatch v2, contract C).

One shared reader, used by both `contig status` (one-shot) and `contig watch`
(redraw loop), so the two commands never drift. It derives the snapshot from the
files a run writes as it goes: status.json (state + timing), trace.txt (task
progress, columns resolved by header), and repair_progress.jsonl (live self-heal
attempts). Every file may be absent early in a run; the reader stays honest and
reports what it can.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel

from contig.events import parse_trace_file

# Trace statuses Nextflow writes; we only key off COMPLETED / RUNNING here.
_COMPLETED = "COMPLETED"
_RUNNING = "RUNNING"


class RunningTask(BaseModel):
    """A task currently executing, named for the live view."""

    process: str
    name: str | None = None


class RepairStepLite(BaseModel):
    """A self-heal attempt as the live view needs it (no nested patch detail)."""

    attempt: int
    failure_class: str
    outcome: str


class ProgressSnapshot(BaseModel):
    """A point-in-time view of a run, derived from its on-disk progress files."""

    run_id: str
    state: str  # running | finished | interrupted | error | missing
    started_at: str | None = None
    elapsed_sec: float | None = None
    tasks_completed: int = 0
    tasks_running: list[RunningTask] = []
    submitted: int | None = None  # total trace rows, or None if no trace yet
    repairs: list[RepairStepLite] = []


def render_progress(snapshot: ProgressSnapshot) -> str:
    """Render a snapshot as a compact, terminal-friendly block.

    Factored from the watch loop so the rendering is testable without sleeping.
    Stays honest: shows the completed count and running steps, and a progress
    fraction only when the submitted total is known (never a fabricated percent).
    """
    lines = [f"Run {snapshot.run_id}: {snapshot.state.upper()}"]
    if snapshot.elapsed_sec is not None:
        lines.append(f"Elapsed: {snapshot.elapsed_sec:.0f}s")
    if snapshot.submitted is not None:
        lines.append(f"Tasks: {snapshot.tasks_completed} of {snapshot.submitted} completed")
    else:
        lines.append(f"Tasks: {snapshot.tasks_completed} completed")
    if snapshot.tasks_running:
        lines.append("Running:")
        for task in snapshot.tasks_running:
            lines.append(f"  - {task.process}")
    if snapshot.repairs:
        last = snapshot.repairs[-1]
        lines.append(
            f"Last repair: attempt {last.attempt} ({last.failure_class}): {last.outcome}"
        )
    return "\n".join(lines)


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _read_status(run_dir: Path) -> dict:
    path = run_dir / "status.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except (ValueError, OSError):
        return {}


def _read_repairs(run_dir: Path) -> list[RepairStepLite]:
    path = run_dir / "repair_progress.jsonl"
    if not path.exists():
        return []
    repairs: list[RepairStepLite] = []
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        try:
            data = json.loads(line)
        except ValueError:
            continue
        repairs.append(
            RepairStepLite(
                attempt=data["attempt"],
                failure_class=data["diagnosis"]["failure_class"],
                outcome=data["outcome"],
            )
        )
    return repairs


def read_progress(runs_dir: str | Path, run_id: str) -> ProgressSnapshot:
    """Read a run's live progress from status.json, trace.txt, and repair_progress.jsonl.

    A run with no status.json is reported as "missing" rather than guessed at, so
    a never-started or wrong id is never dressed up as running.
    """
    run_dir = Path(runs_dir) / run_id
    status = _read_status(run_dir)
    if not status:
        return ProgressSnapshot(run_id=run_id, state="missing")

    started_at = status.get("started_at")
    finished_at = status.get("finished_at")
    elapsed_sec: float | None = None
    start_dt = _parse_iso(started_at)
    if start_dt is not None:
        end_dt = _parse_iso(finished_at) or datetime.now(start_dt.tzinfo)
        elapsed_sec = (end_dt - start_dt).total_seconds()

    completed = 0
    running: list[RunningTask] = []
    submitted: int | None = None
    trace_path = run_dir / "trace.txt"
    if trace_path.exists():
        events = parse_trace_file(trace_path)
        submitted = len(events)
        for event in events:
            upper = event.status.upper()
            if upper == _COMPLETED:
                completed += 1
            elif upper == _RUNNING:
                running.append(RunningTask(process=event.process, name=event.name))

    return ProgressSnapshot(
        run_id=run_id,
        state=status.get("state", "missing"),
        started_at=started_at,
        elapsed_sec=elapsed_sec,
        tasks_completed=completed,
        tasks_running=running,
        submitted=submitted,
        repairs=_read_repairs(run_dir),
    )
