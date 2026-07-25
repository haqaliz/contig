"""Tests for the pure stall decision core (heartbeat stall watchdog, capability A1/A2).

`evaluate_stall` decides whether a run has stalled from two heartbeat
fingerprints (mtimes/sizes of the surfaces a running pipeline touches) plus the
timestamp of the last observed change. Pure: no subprocess, no filesystem, no
sleeping. The observer that produces `Heartbeat` values by stat()-ing real files
lives in this module too (off-thread, per D1 in the plan), but is exercised
separately below from the decision math.
"""

import threading

from contig.stall import (
    Heartbeat,
    changed,
    evaluate_stall,
    observe_with_deadline,
    read_heartbeat,
    stall_message,
)


def _hb(**overrides) -> Heartbeat:
    base = dict(
        trace_mtime=1.0,
        trace_size=100,
        nflog_mtime=1.0,
        nflog_size=200,
        runlog_size=300,
    )
    base.update(overrides)
    return Heartbeat(**base)


def test_changed_true_when_first_observation():
    # previous is None => a run that just started is alive, not stalled.
    assert changed(None, _hb()) is True


def test_changed_false_when_identical():
    previous = _hb()
    current = _hb()
    assert changed(previous, current) is False


def test_changed_true_when_any_field_differs():
    previous = _hb()
    current = _hb(trace_size=101)
    assert changed(previous, current) is True


def test_changed_true_when_surface_goes_from_value_to_none():
    # Something happened: the surface stopped being observable.
    previous = _hb(runlog_size=300)
    current = _hb(runlog_size=None)
    assert changed(previous, current) is True


def test_changed_false_when_surface_stays_none_to_none():
    previous = _hb(runlog_size=None)
    current = _hb(runlog_size=None)
    assert changed(previous, current) is False


def test_evaluate_stall_not_stalled_when_changed():
    decision = evaluate_stall(
        previous=_hb(trace_size=100),
        current=_hb(trace_size=101),
        last_change_at=0.0,
        now=9999.0,
        timeout_sec=3600.0,
    )
    assert decision.stalled is False
    assert decision.idle_sec == 0.0
    assert decision.silent_surfaces == ()


def test_evaluate_stall_idle_below_timeout_not_stalled():
    decision = evaluate_stall(
        previous=_hb(),
        current=_hb(),
        last_change_at=0.0,
        now=100.0,
        timeout_sec=3600.0,
    )
    assert decision.stalled is False
    assert decision.idle_sec == 100.0
    assert decision.silent_surfaces == ("trace.txt", ".nextflow.log", "run.log")


def test_evaluate_stall_idle_at_or_past_timeout_is_stalled():
    decision = evaluate_stall(
        previous=_hb(),
        current=_hb(),
        last_change_at=0.0,
        now=3600.0,
        timeout_sec=3600.0,
    )
    assert decision.stalled is True
    assert decision.idle_sec == 3600.0
    assert decision.silent_surfaces == ("trace.txt", ".nextflow.log", "run.log")


def test_evaluate_stall_timeout_zero_never_stalls():
    decision = evaluate_stall(
        previous=_hb(),
        current=_hb(),
        last_change_at=0.0,
        now=10**9,
        timeout_sec=0.0,
    )
    assert decision.stalled is False


def test_evaluate_stall_timeout_negative_never_stalls():
    decision = evaluate_stall(
        previous=_hb(),
        current=_hb(),
        last_change_at=0.0,
        now=10**9,
        timeout_sec=-1.0,
    )
    assert decision.stalled is False


def test_evaluate_stall_clamps_idle_sec_at_zero_when_clock_goes_backwards():
    # time.monotonic() cannot go backwards, but an injected clock (tests, or a
    # future non-monotonic source) can. A negative idle_sec is nonsensical.
    decision = evaluate_stall(
        previous=_hb(),
        current=_hb(),
        last_change_at=100.0,
        now=50.0,
        timeout_sec=3600.0,
    )
    assert decision.idle_sec == 0.0
    assert decision.stalled is False


def test_stall_message_contains_needles_the_detector_keys_on():
    msg = stall_message(
        idle_sec=3600.0,
        timeout_sec=3600.0,
        silent_surfaces=("trace.txt", ".nextflow.log", "run.log"),
    )
    assert "contig watchdog" in msg
    assert "no forward progress" in msg
    assert "3600s" in msg
    assert "trace.txt" in msg
    assert ".nextflow.log" in msg
    assert "run.log" in msg


def test_read_heartbeat_reads_stat_of_all_three_surfaces(tmp_path):
    artifact_path = tmp_path / "trace.txt"
    artifact_path.write_text("a-row\n")
    (tmp_path / ".nextflow.log").write_text("log line\n")
    (tmp_path / "run.log").write_text("stdout capture\n")

    hb = read_heartbeat(tmp_path, artifact_path)

    trace_stat = artifact_path.stat()
    nflog_stat = (tmp_path / ".nextflow.log").stat()
    runlog_stat = (tmp_path / "run.log").stat()
    assert hb.trace_mtime == trace_stat.st_mtime
    assert hb.trace_size == trace_stat.st_size
    assert hb.nflog_mtime == nflog_stat.st_mtime
    assert hb.nflog_size == nflog_stat.st_size
    assert hb.runlog_size == runlog_stat.st_size


def test_read_heartbeat_missing_files_degrade_to_none_without_raising(tmp_path):
    # No trace.txt, no .nextflow.log, no run.log: a run that hasn't written
    # anything yet is normal, not an error (and parse_trace_file would raise
    # FileNotFoundError here — read_heartbeat must not call it).
    artifact_path = tmp_path / "trace.txt"

    hb = read_heartbeat(tmp_path, artifact_path)

    assert hb == Heartbeat(
        trace_mtime=None,
        trace_size=None,
        nflog_mtime=None,
        nflog_size=None,
        runlog_size=None,
    )


def test_read_heartbeat_run_dir_itself_missing_does_not_raise(tmp_path):
    # The run dir doesn't exist at all yet — stat() on run_dir / ".nextflow.log"
    # still just raises FileNotFoundError, which must degrade to None.
    missing_run_dir = tmp_path / "no-such-run-dir"
    artifact_path = missing_run_dir / "trace.txt"

    hb = read_heartbeat(missing_run_dir, artifact_path)

    assert hb == Heartbeat(None, None, None, None, None)


def test_observe_with_deadline_returns_observer_result_within_deadline():
    fast_result = _hb(trace_size=999)

    def fast_observer(run_dir, artifact_path):
        return fast_result

    hb = observe_with_deadline(
        fast_observer,
        run_dir=None,
        artifact_path=None,
        previous=_hb(),
        deadline_sec=5.0,
    )

    assert hb is fast_result


def test_observe_with_deadline_returns_previous_when_observer_blocks_past_deadline():
    # A fake observer that genuinely blocks (never sets the Event) simulates a
    # wedged NFS stat(): a real stat() there blocks uninterruptibly, so nothing
    # short of "stop waiting on it" can recover. Bounded here by a short
    # deadline so the test itself cannot hang the suite; the daemon thread is
    # abandoned, not joined further.
    never_set = threading.Event()
    previous = _hb(trace_size=42)

    def blocking_observer(run_dir, artifact_path):
        never_set.wait()  # never returns within the test
        return _hb(trace_size=999)  # pragma: no cover - unreachable in test

    hb = observe_with_deadline(
        blocking_observer,
        run_dir=None,
        artifact_path=None,
        previous=previous,
        deadline_sec=0.05,
    )

    assert hb == previous


def test_observe_with_deadline_returns_all_none_heartbeat_when_no_previous_and_blocked():
    never_set = threading.Event()

    def blocking_observer(run_dir, artifact_path):
        never_set.wait()
        return _hb()  # pragma: no cover - unreachable in test

    hb = observe_with_deadline(
        blocking_observer,
        run_dir=None,
        artifact_path=None,
        previous=None,
        deadline_sec=0.05,
    )

    assert hb == Heartbeat(
        trace_mtime=None,
        trace_size=None,
        nflog_mtime=None,
        nflog_size=None,
        runlog_size=None,
    )


def test_observe_with_deadline_returns_previous_when_observer_raises():
    # A failed observation and a timed-out observation are the same fact: "no
    # progress observed". An observer that raises (e.g. a future non-stat
    # observer, or Path.stat() raising ValueError on an embedded null byte —
    # not an OSError) must degrade honestly like the timeout path, not crash
    # the watchdog that is supposed to be protecting a healthy run.
    previous = _hb(trace_size=42)

    def raising_observer(run_dir, artifact_path):
        raise ValueError("boom")

    hb = observe_with_deadline(
        raising_observer,
        run_dir=None,
        artifact_path=None,
        previous=previous,
        deadline_sec=5.0,
    )

    assert hb == previous


def test_observe_with_deadline_returns_all_none_heartbeat_when_no_previous_and_observer_raises():
    def raising_observer(run_dir, artifact_path):
        raise ValueError("boom")

    hb = observe_with_deadline(
        raising_observer,
        run_dir=None,
        artifact_path=None,
        previous=None,
        deadline_sec=5.0,
    )

    assert hb == Heartbeat(
        trace_mtime=None,
        trace_size=None,
        nflog_mtime=None,
        nflog_size=None,
        runlog_size=None,
    )


def test_stall_message_never_contains_oom_or_time_limit_needles():
    # These substrings would collide with the OOM/time-limit detector branches
    # (detect.py), which must win outright on their own evidence. A future
    # reword of this message must not silently reintroduce that collision.
    msg = stall_message(
        idle_sec=7200.0,
        timeout_sec=3600.0,
        silent_surfaces=("trace.txt", ".nextflow.log", "run.log"),
    )
    lowered = msg.lower()
    for forbidden in ("killed", "oom", "out of memory", "time limit"):
        assert forbidden not in lowered
