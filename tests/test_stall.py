"""Tests for the pure stall decision core (heartbeat stall watchdog, capability A1/A2).

`evaluate_stall` decides whether a run has stalled from two heartbeat
fingerprints (mtimes/sizes of the surfaces a running pipeline touches) plus the
timestamp of the last observed change. Pure: no subprocess, no filesystem, no
sleeping. The observer that produces `Heartbeat` values by stat()-ing real files
lives elsewhere (off-thread, per D1 in the plan); these tests exercise the
decision math alone.
"""

from contig.stall import Heartbeat, changed, evaluate_stall, stall_message


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
