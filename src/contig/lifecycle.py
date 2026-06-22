"""In-run lifecycle controls: cancel and resume (PRD contracts A, B).

These are the human-in-the-loop controls over a run already in flight. `cancel`
reaps the run's process group and writes a terminal `cancelled` status; `resume`
rebuilds the original invocation from launch.json and re-runs the SAME run id in
the SAME run dir with Nextflow -resume so cached tasks are reused.

Process control lives here, behind a clean function boundary, so the CLI stays a
thin validating shell and the kill/decision logic is testable without spawning
real Nextflow.
"""

from __future__ import annotations

import json
import os
import signal
import time
from datetime import datetime, timezone
from pathlib import Path

from contig.notify import emit_event

# A run can only be cancelled while it is doing work: actively running or paused
# waiting for an approval. Anything else has already reached a terminal state.
_ACTIVE_STATES = {"running", "awaiting_approval"}


class CancelError(Exception):
    """Raised when there is no active run to cancel (already done, or no status)."""


class ResumeError(Exception):
    """Raised when a run is not in a resumable state (finished, live, or absent)."""


def _read_status(run_dir: Path) -> dict | None:
    path = run_dir / "status.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (ValueError, OSError):
        return None


def _write_terminal_status(run_dir: Path, status: dict, state: str) -> None:
    """Persist a terminal status, preserving started_at and stamping finished_at."""
    now = datetime.now(timezone.utc).isoformat()
    status = dict(status)
    status["state"] = state
    status["finished_at"] = now
    status.setdefault("started_at", now)
    (run_dir / "status.json").write_text(json.dumps(status))


def _pid_alive(pid: int) -> bool:
    """True if the process is still around (signal 0 is a liveness probe)."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # It exists but is owned by another user; treat it as alive.
        return True
    return True


def _terminate_process_group(pid: int, wait_seconds: float) -> None:
    """SIGTERM the run's process group, then SIGKILL if it does not exit.

    Runs are spawned detached, so the process group id equals the pid; killing
    the group reaps the Nextflow launcher and its Java/tool children together. A
    pid that is already gone is fine: there is simply nothing left to reap.
    """
    try:
        pgid = os.getpgid(pid)
    except ProcessLookupError:
        return  # already gone
    try:
        os.killpg(pgid, signal.SIGTERM)
    except ProcessLookupError:
        return
    if wait_seconds > 0:
        time.sleep(wait_seconds)
    if _pid_alive(pid):
        try:
            os.killpg(pgid, signal.SIGKILL)
        except ProcessLookupError:
            return


def cancel_run(runs_dir: str | Path, run_id: str, *, wait_seconds: float = 2.0) -> None:
    """Cancel an active run: reap its process group, then write `cancelled` state.

    Refuses (raises CancelError) when the run is not active: a finished, errored,
    already-cancelled, or unknown run has nothing to cancel. If the run says it is
    active but the process is already dead, the terminal state is still written so
    a stale "running" never lingers.
    """
    run_dir = Path(runs_dir) / run_id
    status = _read_status(run_dir)
    if status is None:
        raise CancelError(f"no run {run_id!r} found in {runs_dir} (nothing to cancel)")
    state = status.get("state")
    if state not in _ACTIVE_STATES:
        raise CancelError(f"run {run_id!r} is {state!r}, not active (nothing to cancel)")

    pid = status.get("pid")
    if isinstance(pid, int):
        _terminate_process_group(pid, wait_seconds)
    _write_terminal_status(run_dir, status, "cancelled")
    emit_event(runs_dir, run_id, "cancelled", f"Run {run_id} was cancelled.")


def write_approval(runs_dir: str | Path, run_id: str, *, approve: bool) -> None:
    """Write runs/<id>/approval.json, the human's decision on a gated patch.

    The self-heal loop's poll reads this `{decision, decided_at}` to either apply
    the gated patch and retry (approve) or stop (reject) (PRD contract C).
    """
    run_dir = Path(runs_dir) / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "approval.json").write_text(
        json.dumps(
            {
                "decision": "approve" if approve else "reject",
                "decided_at": datetime.now(timezone.utc).isoformat(),
            }
        )
    )


def resumable_state(runs_dir: str | Path, run_id: str) -> None:
    """Validate that a run can be resumed; raise ResumeError otherwise.

    A run is resumable when it was cancelled, or when it is "interrupted": its
    status still says running but the process is dead (the dashboard-derived
    state that is never written to disk). A live running run, a finished/errored
    run, and an unknown run are all refused.
    """
    run_dir = Path(runs_dir) / run_id
    status = _read_status(run_dir)
    if status is None:
        raise ResumeError(f"no run {run_id!r} found in {runs_dir} (nothing to resume)")
    state = status.get("state")
    if state == "cancelled":
        return
    pid = status.get("pid")
    if state == "running" and isinstance(pid, int) and not _pid_alive(pid):
        return  # interrupted: running on disk, but the process is gone
    raise ResumeError(f"run {run_id!r} is {state!r}, not resumable")
