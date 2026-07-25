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


def _is_real_pid(value: object) -> bool:
    """True for an actual int pid/pgid, not the bool subclass of int.

    isinstance(True, int) is True in Python, so a plain `isinstance(x, int)`
    guard lets a hand-edited or corrupted status.json's JSON `true` through
    as pid 1 -- init/launchd's process group. No writer in this codebase has
    ever produced a bool here; this exists purely so a corrupted file can't
    signal it.
    """
    return isinstance(value, int) and not isinstance(value, bool)


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
    """SIGTERM the process group containing pid, then SIGKILL if it does not exit.

    Two different callers rely on this, and both work because os.getpgid(pid)
    resolves whichever group pid currently belongs to, whether or not pid is
    that group's leader:

    - the run's own pid (status.json's `pid`), whose group is shared with an
      inherited, non-detached child -- true for every run that predates the
      stall watchdog, and for the watchdog's own supervising process;
    - a watchdog-spawned child's pgid (status.json's `child_pgid`), which is
      also a valid pid to pass here: `start_new_session=True` makes that child
      a session leader, and a session leader's pid equals its own pgid.

    A pid that is already gone is fine: there is simply nothing left to reap.
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

    `wait_seconds` is the SIGTERM grace period, spent once PER process group.
    A watchdog run that has both a live `child_pgid` and its own `pid` group
    can therefore take up to 2x `wait_seconds` to cancel, not `wait_seconds` --
    a rare admin action taking longer is an acceptable trade against the
    complexity of a single shared grace window across two independent groups.
    """
    run_dir = Path(runs_dir) / run_id
    status = _read_status(run_dir)
    if status is None:
        raise CancelError(f"no run {run_id!r} found in {runs_dir} (nothing to cancel)")
    state = status.get("state")
    if state not in _ACTIVE_STATES:
        raise CancelError(f"run {run_id!r} is {state!r}, not active (nothing to cancel)")

    # Child group first, then the run's own (D2): the watchdog's detached
    # child must die before its supervisor, so the pipeline never outlives the
    # process that would otherwise clean up after it.
    #
    # child_pgid can legitimately be absent even on a run this watchdog is
    # actively supervising, not just on a run predating it: self_heal's
    # _write_status (self_heal.py:207-234) writes a fresh status dict rather
    # than merging, so every state-transition write between retry attempts
    # clobbers the key. That window never overlaps a live child -- those
    # writes all happen after run_pipeline has returned, and the next
    # attempt's executor republishes a fresh child_pgid before its own child
    # runs -- so treating "absent" as "nothing extra to reap" is correct for
    # every cause, not merely a back-compat shim for pre-watchdog runs.
    #
    # The mirror case -- present but STALE -- also happens: self_heal's
    # auto_approve retry branch (self_heal.py:1041-1063), unlike the other two
    # retry branches, never calls _write_status before its `continue`, so the
    # PREVIOUS attempt's dead child_pgid lingers in status.json until the next
    # attempt's executor overwrites it. Still safe: nothing detached is alive
    # in that window (anything run synchronously in between, e.g. an index
    # build, is undetached and reaped via the `pid` path below), and reaping a
    # stale pgid is exactly what _terminate_process_group's ProcessLookupError
    # handling is for.
    child_pgid = status.get("child_pgid")
    if _is_real_pid(child_pgid):
        _terminate_process_group(child_pgid, wait_seconds)
    pid = status.get("pid")
    if _is_real_pid(pid):
        _terminate_process_group(pid, wait_seconds)
    _write_terminal_status(run_dir, status, "cancelled")
    emit_event(runs_dir, run_id, "cancelled", f"Run {run_id} was cancelled.")


def write_approval(
    runs_dir: str | Path, run_id: str, *, approve: bool, choice: int | None = None
) -> None:
    """Write runs/<id>/approval.json, the human's decision on a gated patch.

    The self-heal loop's poll reads this `{decision, decided_at, choice?}` to either
    apply the gated patch and retry (approve) or stop (reject) (PRD contracts C, D).
    On a CHOICE gate (the pending request carried a ranked `options` array), `choice`
    is the picked option index; the loop validates it against the options length, so
    an out-of-range index is refused, not applied. It is omitted on the single gate.
    """
    run_dir = Path(runs_dir) / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    decision = {
        "decision": "approve" if approve else "reject",
        "decided_at": datetime.now(timezone.utc).isoformat(),
    }
    if choice is not None:
        decision["choice"] = choice
    (run_dir / "approval.json").write_text(json.dumps(decision))


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
