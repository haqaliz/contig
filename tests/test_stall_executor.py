"""Tests for the watchdog executor (heartbeat stall watchdog, capability A7).

`make_watchdog_executor` returns an `Executor` — the exact
`(cmd, trace_path) -> int` seam `run_pipeline` already calls — that supervises
a real child process and terminates it when the heartbeat says the run has made
no forward progress.

Real child processes are used deliberately here: the terminate ladder (process
group, SIGTERM, grace, SIGKILL) and the run.log flush ordering are exactly the
things a fake `Popen` would let us get wrong. The clock, the sleeper and the
heartbeat observer are injected, so nothing waits a real timeout, and every test
is bounded by a child that either exits on its own or is killed.
"""

import inspect
import json
import logging
import os
import signal
import sys
import threading
import time

import pytest

from contig.detect import diagnose_failure
from contig.models import TaskEvent
from contig.runner import (
    _write_stall_message,
    default_executor,
    make_watchdog_executor,
    run_pipeline,
)
from contig.stall import Heartbeat

# A child that will never finish on its own: the thing a stall watchdog exists
# to deal with. 60s is far longer than any test's own bound, so if the watchdog
# fails to kill it the test fails on the return code, it does not hang.
HANGING_CHILD = [sys.executable, "-c", "import time; time.sleep(60)"]


def _hb(size: int = 100) -> Heartbeat:
    return Heartbeat(
        trace_mtime=1.0,
        trace_size=size,
        nflog_mtime=1.0,
        nflog_size=size,
        runlog_size=size,
    )


def _silent_observer():
    """An observer whose fingerprint never changes: the definition of a stall."""
    return lambda run_dir, artifact_path: _hb()


def _moving_observer():
    """An observer whose fingerprint changes every read: a healthy run."""
    counter = iter(range(1, 10_000))

    return lambda run_dir, artifact_path: _hb(next(counter))


def _observer_waiting_for(log_path, needle: str, timeout: float = 5.0):
    """A silent observer that first blocks until `needle` shows up in the log.

    Lets a test synchronise on something the child printed before the watchdog is
    allowed to reach a verdict. Bounded by `timeout` so it can never hang the
    suite: if the needle never arrives the observation proceeds anyway and the
    assertion, not the clock, is what fails.
    """

    def _observe(run_dir, artifact_path) -> Heartbeat:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                if needle in log_path.read_text():
                    break
            except OSError:
                pass
            time.sleep(0.01)
        return _hb()

    return _observe


def _sleeper_raising_once(log_path, needle: str, exc: BaseException, timeout: float = 5.0):
    """A sleeper that waits for `needle` in the log, then raises `exc`.

    Simulates the operator hitting Ctrl-C mid-supervision, at a point where the
    child is demonstrably up (it has printed) so the test can assert on its fate.
    """

    def _sleep(_seconds: float) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                if needle in log_path.read_text():
                    break
            except OSError:
                pass
            time.sleep(0.01)
        raise exc

    return _sleep


def _assert_process_gone(pid: int, timeout: float = 5.0) -> None:
    """Wait (briefly) for `pid` to disappear, failing if it is still around."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return
        time.sleep(0.01)
    raise AssertionError(f"process {pid} is still alive; the run was orphaned")


def _stepping_clock(step: float):
    """A monotonic-shaped clock that jumps `step` seconds per read.

    Lets a test cross an hour-long timeout in two polls without sleeping.
    """
    state = {"t": 0.0}

    def _clock() -> float:
        now = state["t"]
        state["t"] += step
        return now

    return _clock


def _killpg_spy(monkeypatch):
    """Record the signals sent to process groups, while still really sending them."""
    sent = []
    real_killpg = os.killpg

    def _spy(pgid, sig):
        sent.append(sig)
        real_killpg(pgid, sig)

    monkeypatch.setattr(os, "killpg", _spy)
    return sent


def test_non_positive_timeout_delegates_to_default_executor(tmp_path, monkeypatch):
    # A disabled watchdog must not spawn, poll, or supervise anything: it is the
    # plain executor, byte for byte, so wiring it by mistake changes nothing.
    calls = []

    def fake_default(cmd, trace_path):
        calls.append((cmd, trace_path))
        return 7

    monkeypatch.setattr("contig.runner.default_executor", fake_default)
    trace_path = tmp_path / "trace.txt"

    executor = make_watchdog_executor(stall_timeout_sec=0)
    assert executor([sys.executable, "-c", "pass"], trace_path) == 7
    assert calls == [([sys.executable, "-c", "pass"], trace_path)]


def test_negative_timeout_delegates_to_default_executor(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(
        "contig.runner.default_executor", lambda cmd, tp: calls.append(cmd) or 0
    )

    executor = make_watchdog_executor(stall_timeout_sec=-1.0)
    assert executor(["x"], tmp_path / "trace.txt") == 0
    assert calls == [["x"]]


def test_stalled_child_is_terminated_and_leaves_the_message_in_run_log(
    tmp_path, monkeypatch
):
    # The whole feature in one test: a child that would run forever, an observer
    # that reports silence, and a clock that walks past the timeout. The child
    # must die, the exit code must be non-zero (so run_pipeline raises), and the
    # sentinel must be in run.log -- it is the detector's only input.
    sent = _killpg_spy(monkeypatch)
    executor = make_watchdog_executor(
        stall_timeout_sec=60.0,
        observer=_silent_observer(),
        clock=_stepping_clock(1000.0),
        sleeper=lambda _seconds: None,
        poll_interval=0.0,
        grace_sec=1.0,
    )

    returncode = executor(HANGING_CHILD, tmp_path / "trace.txt")

    assert returncode == -signal.SIGTERM
    # Python reports a signalled child as a negative code, never 137 (D5); 137
    # is the detector's OOM needle and must not be forged by our own kill.
    assert returncode != 137
    assert returncode != 0
    log_text = (tmp_path / "run.log").read_text()
    assert "contig watchdog" in log_text
    assert "no forward progress" in log_text
    # Terminated at most once, and SIGTERM was enough: a child that dies inside
    # the grace window is never SIGKILLed.
    assert sent == [signal.SIGTERM]


def test_keyboard_interrupt_kills_the_child_instead_of_orphaning_it(tmp_path):
    # start_new_session takes the child out of contig's process group, so the
    # terminal's Ctrl-C no longer reaches it. Without this handling, interrupting
    # a supervised run stops the SUPERVISOR and leaves Nextflow, its JVM and its
    # containers burning the user's compute -- the exact harm this slice exists
    # to prevent, arriving through a different door.
    log_path = tmp_path / "run.log"
    executor = make_watchdog_executor(
        stall_timeout_sec=3600.0,
        observer=_silent_observer(),
        clock=_stepping_clock(1.0),
        sleeper=_sleeper_raising_once(log_path, "ready", KeyboardInterrupt()),
        # Non-zero, so the pause (and therefore the interrupt) actually happens:
        # a zero interval means "no pause", and the sleeper is never consulted.
        poll_interval=0.5,
        grace_sec=1.0,
    )

    with pytest.raises(KeyboardInterrupt):
        executor(
            [
                sys.executable,
                "-c",
                "import os, time; print('ready', os.getpid(), flush=True);"
                " time.sleep(60)",
            ],
            tmp_path / "trace.txt",
        )

    _assert_process_gone(int(log_path.read_text().split()[1]))


def test_stall_message_write_gives_up_when_the_log_write_blocks():
    # run.log lives in the run dir -- on a wedged NFS mount, the same mount whose
    # silence is what the watchdog just diagnosed. Writing the verdict must not be
    # able to block the kill, so the write is bounded exactly like the heartbeat
    # read is (D1).
    blocked = threading.Event()

    class WedgedLog:
        def write(self, data):
            blocked.wait()  # never returns within the deadline

        def flush(self):
            pass

    try:
        started = time.monotonic()
        landed = _write_stall_message(WedgedLog(), "verdict", 0.05)
        elapsed = time.monotonic() - started
    finally:
        blocked.set()  # release the abandoned daemon thread

    assert landed is False
    assert elapsed < 2.0, "a wedged write held the watchdog past its deadline"


def test_child_is_killed_even_when_the_verdict_never_reaches_the_log(
    tmp_path, monkeypatch
):
    # Fault injection at the write seam: the verdict is lost (wedged mount), and
    # the run must STILL be terminated. Killing is the primary job; the message
    # is evidence that improves the diagnosis.
    monkeypatch.setattr(
        "contig.runner._write_stall_message", lambda log, message, deadline_sec: False
    )
    sent = _killpg_spy(monkeypatch)
    executor = make_watchdog_executor(
        stall_timeout_sec=60.0,
        observer=_silent_observer(),
        clock=_stepping_clock(1000.0),
        sleeper=lambda _seconds: None,
        poll_interval=0.0,
        grace_sec=1.0,
    )

    returncode = executor(HANGING_CHILD, tmp_path / "trace.txt")

    assert returncode == -signal.SIGTERM
    assert sent == [signal.SIGTERM]
    assert "contig watchdog" not in (tmp_path / "run.log").read_text()


def test_normally_exiting_child_keeps_its_own_exit_code_and_is_never_signalled(
    tmp_path, monkeypatch
):
    # The supervisor must be invisible to a run that is behaving: the child's own
    # exit code passes through, its output is captured, and no signal is sent.
    # The clock crawls (1s/poll) against an hour-long timeout, so nothing can
    # stall; the child ends the loop by exiting on its own.
    sent = _killpg_spy(monkeypatch)
    executor = make_watchdog_executor(
        stall_timeout_sec=3600.0,
        observer=_silent_observer(),
        clock=_stepping_clock(1.0),
        sleeper=time.sleep,
        poll_interval=0.01,
    )

    returncode = executor(
        [sys.executable, "-c", "import sys; sys.stdout.write('hello\\n'); sys.exit(3)"],
        tmp_path / "trace.txt",
    )

    assert returncode == 3
    log_text = (tmp_path / "run.log").read_text()
    assert "hello" in log_text
    assert "contig watchdog" not in log_text
    assert sent == []


def test_early_exit_is_noticed_without_waiting_out_the_poll_interval(tmp_path):
    # Real sleeper, production-sized 30s poll interval, child gone in milliseconds.
    # A blind sleep-then-poll loop would not notice until t=30s, and the self-heal
    # loop's fast failures (bad argv, missing reference) would pay that per
    # attempt. This test uses wall-clock time deliberately -- the latency IS the
    # behavior under test.
    executor = make_watchdog_executor(
        stall_timeout_sec=3600.0,
        observer=_silent_observer(),
        clock=_stepping_clock(1.0),
        sleeper=time.sleep,
        poll_interval=30.0,
    )

    started = time.monotonic()
    returncode = executor(
        [sys.executable, "-c", "import sys; sys.exit(4)"], tmp_path / "trace.txt"
    )
    elapsed = time.monotonic() - started

    assert returncode == 4
    assert elapsed < 5.0, f"waited {elapsed:.1f}s for a child that exited immediately"


def test_observer_reporting_change_never_terminates(tmp_path, monkeypatch):
    # Motion on any surface resets the idle window. Even with a clock that jumps
    # a full timeout every poll, a run whose fingerprint keeps changing is alive
    # and must be left alone -- this is what stops a slow-but-working pipeline
    # from being killed.
    sent = _killpg_spy(monkeypatch)
    executor = make_watchdog_executor(
        stall_timeout_sec=1.0,
        observer=_moving_observer(),
        clock=_stepping_clock(1000.0),
        sleeper=time.sleep,
        poll_interval=0.01,
    )

    returncode = executor(
        [sys.executable, "-c", "import time; time.sleep(0.2)"], tmp_path / "trace.txt"
    )

    assert returncode == 0
    assert sent == []
    assert "contig watchdog" not in (tmp_path / "run.log").read_text()


def test_child_that_ignores_sigterm_is_sigkilled_after_the_grace_window(
    tmp_path, monkeypatch
):
    # The second rung of the ladder (D5). Nextflow trapping SIGTERM and refusing
    # to die is exactly the case a bare terminate() would leave burning compute.
    sent = _killpg_spy(monkeypatch)
    executor = make_watchdog_executor(
        stall_timeout_sec=60.0,
        # Hold the first observation until the child has actually installed its
        # SIGTERM handler, otherwise the kill can win the race and the test
        # flakes on -15 instead of proving the escalation.
        observer=_observer_waiting_for(tmp_path / "run.log", "ready"),
        clock=_stepping_clock(1000.0),
        sleeper=lambda _seconds: None,
        poll_interval=0.0,
        grace_sec=0.2,
        stat_deadline_sec=30.0,
    )

    returncode = executor(
        [
            sys.executable,
            "-c",
            "import signal, time; signal.signal(signal.SIGTERM, signal.SIG_IGN);"
            " print('ready', flush=True); time.sleep(60)",
        ],
        tmp_path / "trace.txt",
    )

    assert returncode == -signal.SIGKILL
    assert returncode != 137
    assert sent == [signal.SIGTERM, signal.SIGKILL]
    assert "contig watchdog" in (tmp_path / "run.log").read_text()


def test_stall_message_is_appended_without_overwriting_the_child_output(
    tmp_path, monkeypatch
):
    # run.log is the child's stdout AND the file the watchdog writes its verdict
    # into, so two processes are writing one file. Pins that both survive in
    # full: every line the child emitted is intact AND the verdict is there.
    # (Interleaving is what a naive implementation gets wrong -- a write at a
    # stale offset lands on top of captured output, destroying the very log the
    # detector reads.)
    _killpg_spy(monkeypatch)
    lines = 200
    chatty_child = [
        sys.executable,
        "-c",
        "import sys, time\n"
        f"for i in range({lines}):\n"
        "    sys.stdout.write('tick %04d\\n' % i)\n"
        "sys.stdout.flush()\n"
        "time.sleep(60)\n",
    ]
    executor = make_watchdog_executor(
        stall_timeout_sec=60.0,
        # Only judge the run once every line the child meant to write is on disk.
        observer=_observer_waiting_for(tmp_path / "run.log", f"tick {lines - 1:04d}"),
        clock=_stepping_clock(1000.0),
        sleeper=lambda _seconds: None,
        poll_interval=0.0,
        grace_sec=1.0,
        stat_deadline_sec=30.0,
    )

    executor(chatty_child, tmp_path / "trace.txt")

    log_text = (tmp_path / "run.log").read_text()
    assert "contig watchdog" in log_text
    for i in range(lines):
        assert f"tick {i:04d}" in log_text, f"child output line {i} was overwritten"


def _pgid_reporting_child(hold_sec: float = 0.3) -> list[str]:
    """A child that prints its own process-group id, then lingers briefly.

    The print is how a test learns the pgid to assert against; the lingering is
    what keeps `os.getpgid(child)` answerable while the executor records it.
    """
    return [
        sys.executable,
        "-c",
        f"import os, time; print(os.getpgid(0), flush=True); time.sleep({hold_sec})",
    ]


def _healthy_executor(**overrides):
    """A watchdog configured so nothing can stall: for testing the side effects."""
    kwargs = dict(
        stall_timeout_sec=3600.0,
        observer=_silent_observer(),
        clock=_stepping_clock(1.0),
        sleeper=time.sleep,
        poll_interval=0.01,
    )
    kwargs.update(overrides)
    return make_watchdog_executor(**kwargs)


def test_run_log_is_truncated_so_a_stale_verdict_cannot_leak_into_the_next_attempt(
    tmp_path,
):
    # Every attempt starts from an empty run.log, exactly as default_executor's
    # "wb" does. High consequence if it regresses: self-heal retries the SAME run
    # dir with -resume, so attempt 1's verdict left in place would make the
    # detector re-diagnose no_progress off a stale line and burn the entire repair
    # budget on a run that never stalled again.
    log_path = tmp_path / "run.log"
    log_path.write_text(
        "contig watchdog: no forward progress for 3600s (attempt 1)\n"
        "some older output from attempt 1\n"
    )

    returncode = _healthy_executor()(
        [sys.executable, "-c", "print('attempt 2 output')"], tmp_path / "trace.txt"
    )

    assert returncode == 0
    log_text = log_path.read_text()
    assert "attempt 1" not in log_text
    assert "contig watchdog" not in log_text
    assert "attempt 2 output" in log_text


_ORIGINAL_STATUS = {
    "run_id": "run-1",
    "state": "running",
    "pid": 4242,
    "started_at": "2026-07-25T00:00:00+00:00",
    "finished_at": None,
}


def _write_status_json(tmp_path):
    """Lay down the status.json self_heal would have written before the run."""
    status_path = tmp_path / "status.json"
    status_path.write_text(json.dumps(_ORIGINAL_STATUS))
    return status_path


def _status_snapshotting_observer(status_path, snapshots: list):
    """A silent observer that copies status.json on every poll.

    `child_pgid` is only meaningful WHILE the child is alive, so a test that
    asserts on it has to read the file from inside the supervision loop -- the
    observer is the seam that runs there.
    """

    def _observe(run_dir, artifact_path) -> Heartbeat:
        try:
            snapshots.append(json.loads(status_path.read_text()))
        except (OSError, ValueError):
            pass
        return _hb()

    return _observe


def test_child_pgid_is_merged_into_existing_status_json(tmp_path):
    # D2's other half: detaching the child removes it from the group `contig
    # cancel` reaps, so the child's own pgid has to be published -- WITHOUT
    # clobbering the keys _write_status already put there.
    status_path = _write_status_json(tmp_path)
    snapshots: list = []

    assert (
        _healthy_executor(observer=_status_snapshotting_observer(status_path, snapshots))(
            _pgid_reporting_child(), tmp_path / "trace.txt"
        )
        == 0
    )

    assert snapshots, "the watchdog never polled while the child was alive"
    live = snapshots[0]
    for key, value in _ORIGINAL_STATUS.items():
        assert live[key] == value, f"{key} was clobbered"
    # The recorded pgid is really the child's, and really a NEW group -- not the
    # supervisor's, which is what killpg must never be pointed at.
    child_reported_pgid = int((tmp_path / "run.log").read_text().split()[0])
    assert live["child_pgid"] == child_reported_pgid
    assert live["child_pgid"] != os.getpgid(0)


def test_child_pgid_is_cleared_once_the_child_exits(tmp_path):
    # `child_pgid` means exactly one thing: a detached child is alive RIGHT NOW.
    # _publish_child_pgid already refuses to record a dead child's group because
    # "a recycled pgid would be worse than none"; leaving the key behind after
    # the child exits reintroduces that same hazard from the other end. The
    # self-heal retry branches do not rewrite status.json between attempts, so a
    # stale pgid survives until the next attempt republishes -- and a `contig
    # cancel` landing in that window on a host that has wrapped pid_max would
    # signal an unrelated process group.
    status_path = _write_status_json(tmp_path)

    assert _healthy_executor()(_pgid_reporting_child(), tmp_path / "trace.txt") == 0

    status = json.loads(status_path.read_text())
    assert "child_pgid" not in status, "a dead child's pgid was left behind"
    for key, value in _ORIGINAL_STATUS.items():
        assert status[key] == value, f"{key} was clobbered"


def test_child_pgid_is_cleared_when_the_supervisor_is_interrupted(tmp_path):
    # The other exit from the supervision loop. Ctrl-C kills the child on the way
    # out (see the orphaning test above), so the pgid it published is just as dead
    # as after a normal exit and must not outlive it.
    status_path = _write_status_json(tmp_path)
    log_path = tmp_path / "run.log"
    executor = make_watchdog_executor(
        stall_timeout_sec=3600.0,
        observer=_silent_observer(),
        clock=_stepping_clock(1.0),
        sleeper=_sleeper_raising_once(log_path, "ready", KeyboardInterrupt()),
        poll_interval=0.5,
        grace_sec=1.0,
    )

    with pytest.raises(KeyboardInterrupt):
        executor(
            [
                sys.executable,
                "-c",
                "import os, time; print('ready', os.getpid(), flush=True);"
                " time.sleep(60)",
            ],
            tmp_path / "trace.txt",
        )

    status = json.loads(status_path.read_text())
    assert "child_pgid" not in status, "the interrupt path left a dead pgid behind"
    for key, value in _ORIGINAL_STATUS.items():
        assert status[key] == value, f"{key} was clobbered"


def test_missing_status_json_does_not_fail_the_run(tmp_path, caplog):
    # Publishing the pgid is telemetry for another command; it must never cost
    # the user their run.
    with caplog.at_level(logging.WARNING, logger="contig.runner"):
        returncode = _healthy_executor()(
            [sys.executable, "-c", "import sys; sys.exit(0)"], tmp_path / "trace.txt"
        )

    assert returncode == 0
    assert not (tmp_path / "status.json").exists()
    assert any("child_pgid" in record.getMessage() for record in caplog.records)


def test_unparseable_status_json_is_warned_about_and_left_untouched(tmp_path, caplog):
    # A status file we cannot understand is left exactly as found: overwriting it
    # with a fabricated one would destroy whatever a concurrent writer meant by it.
    status_path = tmp_path / "status.json"
    status_path.write_text("{not json at all")

    with caplog.at_level(logging.WARNING, logger="contig.runner"):
        returncode = _healthy_executor()(
            [sys.executable, "-c", "import sys; sys.exit(0)"], tmp_path / "trace.txt"
        )

    assert returncode == 0
    assert status_path.read_text() == "{not json at all"
    assert any("child_pgid" in record.getMessage() for record in caplog.records)


def test_the_bytes_the_watchdog_writes_really_diagnose_as_no_progress(
    tmp_path, monkeypatch
):
    # The end-to-end coupling, made intentional rather than incidental: take the
    # ACTUAL run.log the executor left behind and hand it to the SHIPPED detector.
    # Everything in between (the message wording, the needles, the branch order)
    # is free to be refactored as long as this holds.
    _killpg_spy(monkeypatch)
    executor = make_watchdog_executor(
        stall_timeout_sec=60.0,
        observer=_silent_observer(),
        clock=_stepping_clock(1000.0),
        sleeper=lambda _seconds: None,
        poll_interval=0.0,
        grace_sec=1.0,
    )

    returncode = executor(HANGING_CHILD, tmp_path / "trace.txt")

    # Killed before Nextflow could write a trace, so there are no events at all --
    # the plan's first edge case. The message alone has to carry the diagnosis.
    diagnosis = diagnose_failure([], (tmp_path / "run.log").read_text())
    assert diagnosis.failure_class == "no_progress"
    assert diagnosis.confidence == 0.9
    assert diagnosis.evidence, "the verdict line itself must be the evidence"
    assert returncode != 0  # so run_pipeline raises and this diagnosis is reached


def test_a_genuine_oom_is_unaffected_by_the_watchdog_branch(tmp_path):
    # The control for the test above: exit 137 with no watchdog line still reads
    # as OOM. Our own kill reports -9/-15 and can never forge 137, so a real
    # out-of-memory kill keeps its diagnosis.
    diagnosis = diagnose_failure(
        [TaskEvent(process="STAR_ALIGN", status="FAILED", exit=137)],
        "Command error:\n  .command.sh: line 9: Killed\n",
    )
    assert diagnosis.failure_class == "oom"


def test_run_pipeline_still_defaults_to_the_plain_executor():
    # Guard the seam from both ends: the watchdog is opt-in, so the default
    # executor `run_pipeline` uses must remain default_executor (Task 6 flips it
    # per-run, never here), and the factory must return something with exactly
    # the Executor shape `(cmd, trace_path)`.
    assert inspect.signature(run_pipeline).parameters["executor"].default is default_executor
    watchdog = make_watchdog_executor(stall_timeout_sec=60.0)
    assert list(inspect.signature(watchdog).parameters) == ["cmd", "trace_path"]
