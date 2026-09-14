"""Tests for the pure peak-RSS memory sizing helper (capability C2).

`peak_informed_memory_gb` sizes an OOM memory retry from the observed peak_rss
in the run's trace via an honest four-tier ladder (OOM'd task's own observed
peak -> same-process sibling peak -> sibling_dominated/blind -> unavailable/blind).
Pure: no I/O, no run. The ceiling-clamp and never-shrink math live later in
apply_patch, so these tests assert the raw sized target the helper returns.
(Same-process sibling rescue ships: the trace parser now carries a coarse
process column, so the sibling key can diverge from the own-task key.)
"""

import math

from contig.models import TaskEvent, TaskResource
from contig.resource_sizing import (
    PEAK_RSS_SAFETY_FACTOR,
    WALLTIME_SAFETY_FACTOR,
    PeakSizing,
    TimeSizing,
    peak_informed_memory_gb,
    realtime_informed_time_h,
)


def _oom_event(process: str, name: str) -> TaskEvent:
    return TaskEvent(process=process, name=name, status="FAILED", exit=137)


def _usage(process: str, name: str, peak_rss_mb: float) -> TaskResource:
    return TaskResource(
        process=process,
        name=name,
        realtime_sec=10.0,
        peak_rss_mb=peak_rss_mb,
        pct_cpu=100.0,
    )


def test_tier_a_oom_task_sizes_off_own_peak():
    events = [_oom_event("STAR_ALIGN", "STAR_ALIGN (S1)")]
    usage = [_usage("STAR_ALIGN", "STAR_ALIGN (S1)", 7800.0)]

    result = peak_informed_memory_gb(events, usage, factor=1.5)

    assert result == PeakSizing(target_gb=12, tier="oom_task", observed_peak_mb=7800.0)
    assert result.target_gb == math.ceil(7800 / 1024 * 1.5)


def test_multi_task_oom_sizes_off_max_peak():
    events = [
        _oom_event("STAR_ALIGN", "STAR_ALIGN (S1)"),
        _oom_event("STAR_ALIGN", "STAR_ALIGN (S2)"),
    ]
    usage = [
        _usage("STAR_ALIGN", "STAR_ALIGN (S1)", 5120.0),
        _usage("STAR_ALIGN", "STAR_ALIGN (S2)", 9216.0),
    ]

    result = peak_informed_memory_gb(events, usage, factor=1.5)

    assert result.tier == "oom_task"
    assert result.observed_peak_mb == 9216.0
    assert result.target_gb == math.ceil(9216 / 1024 * 1.5)


def test_same_process_sibling_rescues_when_strictly_larger():
    # The OOM'd task's own peak is a dash (0), but a same-`process` sibling that
    # completed carries a real peak -> rescue from the sibling's peak. The retry
    # only fires when the sized target strictly exceeds the current limit; here
    # ceil(6144/1024*1.5)=9 > 8, so the sibling rung ships a sized target.
    events = [_oom_event("STAR_ALIGN", "STAR_ALIGN (S1)")]
    usage = [
        _usage("STAR_ALIGN", "STAR_ALIGN (S1)", 0.0),  # killed, dash -> 0
        _usage("STAR_ALIGN", "STAR_ALIGN (S2)", 6144.0),  # completed sibling
    ]

    result = peak_informed_memory_gb(events, usage, factor=1.5, current_gb=8)

    assert result == PeakSizing(
        target_gb=9, tier="sibling_peak", observed_peak_mb=6144.0, source_name="STAR_ALIGN (S2)"
    )


def test_sibling_dominated_falls_back_when_not_strictly_larger():
    # Sibling peak 5120 -> ceil(5120/1024*1.5)=8, which is NOT strictly larger
    # than the current limit 8: sizing at 8 would be a no-op retry with an
    # unchanged limit, so the helper reports sibling_dominated and the caller
    # falls back to the blind multiplier.
    events = [_oom_event("STAR_ALIGN", "STAR_ALIGN (S1)")]
    usage = [
        _usage("STAR_ALIGN", "STAR_ALIGN (S1)", 0.0),  # killed, dash -> 0
        _usage("STAR_ALIGN", "STAR_ALIGN (S2)", 5120.0),  # completed sibling
    ]

    result = peak_informed_memory_gb(events, usage, factor=1.5, current_gb=8)

    assert result == PeakSizing(
        target_gb=None, tier="sibling_dominated", observed_peak_mb=5120.0, source_name="STAR_ALIGN (S2)"
    )


def test_sibling_tier_returns_raw_target_without_current_guard():
    # The current-limit guard is the caller's concern (the blind fallback lives
    # in apply_patch); without `current_gb` the helper returns the raw sized
    # target, matching the tier-a "no clamp in the helper" precedent.
    events = [_oom_event("STAR_ALIGN", "STAR_ALIGN (S1)")]
    usage = [
        _usage("STAR_ALIGN", "STAR_ALIGN (S1)", 0.0),  # killed, dash -> 0
        _usage("STAR_ALIGN", "STAR_ALIGN (S2)", 6144.0),  # completed sibling
    ]

    result = peak_informed_memory_gb(events, usage, factor=1.5)

    assert result.tier == "sibling_peak"
    assert result.target_gb == 9
    assert result.observed_peak_mb == 6144.0
    assert result.source_name == "STAR_ALIGN (S2)"


def test_sibling_tier_unavailable_when_no_positive_sibling():
    # No positive peak anywhere: the killed row is a dash (0) and the sibling
    # row is a dash (0) too -> no evidence at all, so the honest answer is
    # unavailable (distinct from sibling_dominated, which had a real peak).
    events = [_oom_event("STAR_ALIGN", "STAR_ALIGN (S1)")]
    usage = [
        _usage("STAR_ALIGN", "STAR_ALIGN (S1)", 0.0),  # killed, dash -> 0
        _usage("STAR_ALIGN", "STAR_ALIGN (S2)", 0.0),  # sibling also dash -> 0
    ]

    result = peak_informed_memory_gb(events, usage, factor=1.5, current_gb=8)

    assert result == PeakSizing(target_gb=None, tier="unavailable", observed_peak_mb=None)


def test_tier_c_unavailable_when_no_positive_same_process_row():
    events = [_oom_event("STAR_ALIGN", "STAR_ALIGN (S1)")]
    usage = [_usage("STAR_ALIGN", "STAR_ALIGN (S1)", 0.0)]

    result = peak_informed_memory_gb(events, usage, factor=1.5)

    assert result == PeakSizing(target_gb=None, tier="unavailable", observed_peak_mb=None)


def test_tier_c_unavailable_when_no_oom_event():
    events = [TaskEvent(process="STAR_ALIGN", name="STAR_ALIGN (S1)", status="FAILED", exit=1)]
    usage = [_usage("STAR_ALIGN", "STAR_ALIGN (S1)", 4096.0)]

    result = peak_informed_memory_gb(events, usage, factor=1.5)

    assert result == PeakSizing(target_gb=None, tier="unavailable", observed_peak_mb=None)


def test_sub_current_peak_returns_raw_target_no_clamp():
    # Clamping to current happens later in apply_patch; the helper just returns 2.
    events = [_oom_event("SMALL", "SMALL (S1)")]
    usage = [_usage("SMALL", "SMALL (S1)", 800.0)]

    result = peak_informed_memory_gb(events, usage, factor=1.5)

    assert result.target_gb == 2
    assert result.target_gb == math.ceil(800 / 1024 * 1.5)


def test_empty_inputs_are_unavailable():
    assert peak_informed_memory_gb([], []) == PeakSizing(
        target_gb=None, tier="unavailable", observed_peak_mb=None
    )


def test_default_factor_is_the_module_constant():
    assert PEAK_RSS_SAFETY_FACTOR == 1.5


def _usage_rt(process: str, name: str, realtime_sec: float) -> TaskResource:
    return TaskResource(
        process=process,
        name=name,
        realtime_sec=realtime_sec,
        peak_rss_mb=1024.0,
        pct_cpu=100.0,
    )


def test_time_sizes_off_single_realtime_row():
    usage = [_usage_rt("BSMAP", "BSMAP (S1)", 36000.0)]  # 10h

    result = realtime_informed_time_h([], usage)

    assert result == TimeSizing(target_h=15, tier="realtime", observed_realtime_sec=36000.0)


def test_time_sizes_off_max_realtime_across_rows():
    usage = [
        _usage_rt("BSMAP", "BSMAP (S1)", 3600.0),
        _usage_rt("BSMAP", "BSMAP (S2)", 36000.0),
        _usage_rt("BSMAP", "BSMAP (S3)", 7200.0),
    ]

    result = realtime_informed_time_h([], usage)

    assert result.tier == "realtime"
    assert result.observed_realtime_sec == 36000.0
    assert result.target_h == 15


def test_time_returns_raw_target_without_blind_floor():
    # The floor-to-blind (a walltime kill is a censored lower bound) lives in
    # apply_patch; the helper just returns the raw sized target.
    usage = [_usage_rt("BSMAP", "BSMAP (S1)", 14400.0)]  # 4h

    result = realtime_informed_time_h([], usage)

    assert result.target_h == 6  # ceil(4 * 1.5)


def test_time_unavailable_when_all_realtime_zero():
    usage = [
        _usage_rt("BSMAP", "BSMAP (S1)", 0.0),
        _usage_rt("BSMAP", "BSMAP (S2)", 0.0),
    ]

    result = realtime_informed_time_h([], usage)

    assert result == TimeSizing(target_h=None, tier="unavailable", observed_realtime_sec=None)


def test_time_unavailable_when_usage_empty():
    assert realtime_informed_time_h([], []) == TimeSizing(
        target_h=None, tier="unavailable", observed_realtime_sec=None
    )


def test_time_rounds_up_at_ceil_boundary():
    # 3601s -> 3601/3600*1.5 = 1.50041... -> ceil -> 2
    usage = [_usage_rt("BSMAP", "BSMAP (S1)", 3601.0)]

    result = realtime_informed_time_h([], usage)

    assert result.target_h == 2
    assert result.target_h == math.ceil(3601 / 3600 * 1.5)


def test_walltime_default_factor_is_the_module_constant():
    assert WALLTIME_SAFETY_FACTOR == 1.5
