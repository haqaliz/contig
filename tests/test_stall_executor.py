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

import json
import logging
import os
import signal
import sys
import time

from contig.runner import default_executor, make_watchdog_executor
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


def test_child_pgid_is_merged_into_existing_status_json(tmp_path):
    # D2's other half: detaching the child removes it from the group `contig
    # cancel` reaps, so the child's own pgid has to be published -- WITHOUT
    # clobbering the keys _write_status already put there.
    status_path = tmp_path / "status.json"
    original = {
        "run_id": "run-1",
        "state": "running",
        "pid": 4242,
        "started_at": "2026-07-25T00:00:00+00:00",
        "finished_at": None,
    }
    status_path.write_text(json.dumps(original))

    assert _healthy_executor()(_pgid_reporting_child(), tmp_path / "trace.txt") == 0

    status = json.loads(status_path.read_text())
    for key, value in original.items():
        assert status[key] == value, f"{key} was clobbered"
    # The recorded pgid is really the child's, and really a NEW group -- not the
    # supervisor's, which is what killpg must never be pointed at.
    child_reported_pgid = int((tmp_path / "run.log").read_text().split()[0])
    assert status["child_pgid"] == child_reported_pgid
    assert status["child_pgid"] != os.getpgid(0)


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


def test_default_executor_is_still_the_plain_one():
    # Guard the seam: the watchdog is additive, default_executor is untouched.
    assert default_executor.__name__ == "default_executor"
