"""Tests for the pure peak-RSS memory sizing helper (capability C2).

`peak_informed_memory_gb` sizes an OOM memory retry from the observed peak_rss
in the run's trace via a fallback ladder (OOM'd task own peak -> same-process
sibling peak -> unavailable). Pure: no I/O, no run. The ceiling-clamp and
never-shrink math live later in apply_patch, so these tests assert the raw
sized target the helper returns.
"""

import math

from contig.models import TaskEvent, TaskResource
from contig.resource_sizing import (
    PEAK_RSS_SAFETY_FACTOR,
    PeakSizing,
    peak_informed_memory_gb,
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


def test_tier_b_sibling_when_own_row_was_killed():
    events = [_oom_event("STAR_ALIGN", "STAR_ALIGN (S1)")]
    usage = [
        _usage("STAR_ALIGN", "STAR_ALIGN (S1)", 0.0),  # killed, dash -> 0
        _usage("STAR_ALIGN", "STAR_ALIGN (S2)", 6144.0),  # completed sibling
    ]

    result = peak_informed_memory_gb(events, usage, factor=1.5)

    assert result.tier == "sibling"
    assert result.observed_peak_mb == 6144.0
    assert result.target_gb == math.ceil(6144 / 1024 * 1.5)


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
