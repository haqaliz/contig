"""Pure stall decision over heartbeat fingerprints (heartbeat watchdog, no_progress).

A run that is alive keeps touching its output surfaces: `trace.txt` grows a row
per completed task, `.nextflow.log` grows continuously, `run.log` (Contig's own
capture of the child's stdout/stderr) grows whenever the child writes. A `stall`
is the absence of any of that motion for longer than a timeout. This module
knows nothing about processes, signals, or the filesystem — it only compares two
fingerprints and a clock. The observer that stat()s the real files to build a
`Heartbeat` (off-thread, with a stat-deadline so a wedged NFS mount reads as "no
progress" rather than hanging) lives in the executor wiring, not here.

Deliberately honest about what a heartbeat can and cannot know: a surface that
has never existed and one that vanished are both `None`, and the two are
indistinguishable to `changed` on any single observation — only the transition
*into* `None` from a real value is treated as motion (see `changed`).
"""

from __future__ import annotations

from dataclasses import dataclass

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


def stall_message(
    idle_sec: float, timeout_sec: float, silent_surfaces: tuple[str, ...]
) -> str:
    """The single source of the `no_progress` sentinel text.

    The detector keys on the phrase-level needles here ("contig watchdog", "no
    forward progress"). It must NOT contain "killed", "oom", "out of memory", or
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
