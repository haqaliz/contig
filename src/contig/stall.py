"""Stall decision over heartbeat fingerprints (heartbeat watchdog, no_progress).

A run that is alive keeps touching its output surfaces: `trace.txt` grows a row
per completed task, `.nextflow.log` grows continuously, `run.log` (Contig's own
capture of the child's stdout/stderr) grows whenever the child writes. A `stall`
is the absence of any of that motion for longer than a timeout.

Two parts live here. The decision core (`Heartbeat`, `changed`, `evaluate_stall`,
`stall_message`) is pure — it only compares two fingerprints and a clock, and
knows nothing about processes, signals, threads, or timing. The observer
(`read_heartbeat`, `observe_with_deadline`) is the part that actually touches
the filesystem: it `stat()`s the real surfaces off-thread, with a deadline, so a
wedged NFS mount reads as "no progress" rather than hanging the watchdog (D1).
This module still knows nothing about processes or signals — spawning,
terminating, and polling on a cadence are the executor's job (Task 4), not
this one's.

Deliberately honest about what a heartbeat can and cannot know: a surface that
has never existed and one that vanished are both `None`, and the two are
indistinguishable to `changed` on any single observation — only the transition
*into* `None` from a real value is treated as motion (see `changed`).
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

# The literal surface names the detector and the operator-facing message key on.
# Order matches the sentinel text in `stall_message`.
SURFACE_NAMES: tuple[str, ...] = ("trace.txt", ".nextflow.log", "run.log")


@dataclass(frozen=True)
class Heartbeat:
    """A single point-in-time fingerprint of the run's output surfaces.

    Each field is `None` when that surface was not observable at read time
    (doesn't exist yet, or the stat() read didn't return before the observer's
    deadline — see D1 in the plan). Comparable field-for-field by `changed`.
    """

    trace_mtime: float | None
    trace_size: int | None
    nflog_mtime: float | None
    nflog_size: int | None
    runlog_size: int | None


def changed(previous: Heartbeat | None, current: Heartbeat) -> bool:
    """True if any field differs between two consecutive heartbeats.

    A first observation (`previous is None`) counts as changed: a run that has
    just started is alive, not stalled. A surface going from a value to `None`
    counts as changed too — something happened to it (deleted, unmounted,
    read started failing) — but `None` -> `None` is not motion, it is the same
    absence observed twice.
    """
    if previous is None:
        return True
    return (
        previous.trace_mtime != current.trace_mtime
        or previous.trace_size != current.trace_size
        or previous.nflog_mtime != current.nflog_mtime
        or previous.nflog_size != current.nflog_size
        or previous.runlog_size != current.runlog_size
    )


@dataclass(frozen=True)
class StallDecision:
    """The watchdog's verdict for one poll: is the run stalled, and since when."""

    stalled: bool
    idle_sec: float
    silent_surfaces: tuple[str, ...]


def evaluate_stall(
    previous: Heartbeat | None,
    current: Heartbeat,
    last_change_at: float,
    now: float,
    timeout_sec: float,
) -> StallDecision:
    """Decide stall status from two fingerprints, a clock, and a timeout.

    If the surfaces changed since `previous`, the run is alive: `idle_sec` resets
    to 0.0 and `stalled` is False. Otherwise `idle_sec` is how long nothing has
    moved (`now - last_change_at`), and the run is stalled once that reaches
    `timeout_sec`. `timeout_sec <= 0` never stalls — a disabled watchdog (timeout
    left at its zero/negative default) can never fire even if wired by mistake.
    """
    if changed(previous, current):
        return StallDecision(stalled=False, idle_sec=0.0, silent_surfaces=())
    # changed() is False here, which means every field of `current` matched
    # `previous` exactly, so all three named surfaces are trivially silent —
    # no per-surface diffing needed.
    # time.monotonic() cannot go backwards, but an injected clock can; clamp so
    # a negative idle_sec can never masquerade as "just changed".
    idle_sec = max(0.0, now - last_change_at)
    stalled = timeout_sec > 0 and idle_sec >= timeout_sec
    return StallDecision(stalled=stalled, idle_sec=idle_sec, silent_surfaces=SURFACE_NAMES)


# An observer turns a run directory and the trace-file path into a Heartbeat.
# Injected in tests so they never touch a real filesystem; mirrors ApprovalPoll
# (`self_heal.py:297-300`).
HeartbeatObserver = Callable[[Path, Path], Heartbeat]


def read_heartbeat(run_dir: Path, artifact_path: Path) -> Heartbeat:
    """stat() the three output surfaces and fingerprint them.

    Every `OSError` (including `FileNotFoundError` for a surface that has not
    been written yet) degrades that surface's field(s) to `None` — never
    propagates. Deliberately does NOT call `parse_trace_file`: it has no
    existence guard and raises on an absent trace, and we only need `stat()`,
    not the parsed rows.
    """
    trace_stat = _safe_stat(artifact_path)
    nflog_stat = _safe_stat(run_dir / ".nextflow.log")
    runlog_stat = _safe_stat(run_dir / "run.log")
    return Heartbeat(
        trace_mtime=trace_stat.st_mtime if trace_stat else None,
        trace_size=trace_stat.st_size if trace_stat else None,
        nflog_mtime=nflog_stat.st_mtime if nflog_stat else None,
        nflog_size=nflog_stat.st_size if nflog_stat else None,
        runlog_size=runlog_stat.st_size if runlog_stat else None,
    )


def _safe_stat(path: Path):
    try:
        return path.stat()
    except OSError:
        return None


def observe_with_deadline(
    observer: HeartbeatObserver,
    run_dir: Path,
    artifact_path: Path,
    previous: Heartbeat | None,
    deadline_sec: float,
) -> Heartbeat:
    """Run `observer` off-thread so a wedged mount cannot hang the watchdog.

    `stat()` against a hard-mounted, unresponsive NFS blocks in uninterruptible
    sleep — no timeout, no signal, can reach through it (D1 in the plan). So the
    read happens in a **daemon** thread: if it has not returned by `deadline_sec`,
    we stop waiting and keep `previous` (or an all-`None` `Heartbeat` when there
    is no previous yet), which reads as "no progress observed" — the honest
    interpretation, since a filesystem that cannot answer `stat()` is not one on
    which the pipeline is observably progressing. The very first call has no
    `previous` to fall back on, so a mount that is already wedged at process
    start gets one free "no progress" poll before stall accounting begins —
    every poll after that compares against the same all-`None` fallback, so
    `idle_sec` starts accumulating honestly from the second poll on.

    The thread itself is not cancelled and may leak for the life of the wedged
    read. That is acceptable specifically because it is a daemon thread: daemon
    threads never block interpreter exit, so a permanently wedged read cannot
    hang `contig` — it just never contributes its result.

    If `observer` raises instead of hanging, that is the same fact as a
    timeout — "no progress observed" — not a reason to crash the watchdog
    that is supposed to be protecting a healthy run: `Exception` (never
    `BaseException`, so `KeyboardInterrupt`/`SystemExit` still propagate) is
    caught inside the thread and degrades the same way a timeout does.
    """
    result: list[Heartbeat] = []

    def _observe() -> None:
        try:
            result.append(observer(run_dir, artifact_path))
        except Exception:
            pass

    thread = threading.Thread(target=_observe, daemon=True)
    thread.start()
    thread.join(deadline_sec)
    if not thread.is_alive() and result:
        return result[0]
    if previous is None:
        return Heartbeat(
            trace_mtime=None,
            trace_size=None,
            nflog_mtime=None,
            nflog_size=None,
            runlog_size=None,
        )
    return previous


def stall_message(
    idle_sec: float, timeout_sec: float, silent_surfaces: tuple[str, ...]
) -> str:
    """The single source of the `no_progress` sentinel text.

    This string carries ALL of `detect._NO_PROGRESS_NEEDLES` — "no forward
    progress", "no new output or trace update", and "terminating the stalled
    run" — and the detector has no needle beyond them, so this message is the
    single source of the sentinel in both directions. A reword must keep at
    least one of the three or the run stops classifying as `no_progress`. The
    "contig watchdog" prefix is NOT one of them: it is for the human reading
    run.log, and the detector never looks for it. The message must NOT contain
    "killed", "oom", "out of memory", or
    "time limit" — those are the OOM and walltime detector branches' own needles
    (`detect.py`), and OOM must win outright on `exit == 137` regardless of what
    a dying Nextflow also wrote to `trace.txt` (see D6 in the plan). A module-level
    test pins the forbidden substrings' absence so a future reword can't silently
    reintroduce that collision.
    """
    surfaces = ", ".join(silent_surfaces)
    return (
        f"contig watchdog: no forward progress for {idle_sec:.0f}s "
        f"(limit {timeout_sec:.0f}s); no new output or trace update on "
        f"{surfaces}; terminating the stalled run."
    )
