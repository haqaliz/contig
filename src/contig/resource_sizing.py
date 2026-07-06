"""Peak-RSS-informed memory sizing for OOM retries (capability C2, self-heal).

When a task is OOM-killed (exit 137), a blind ``memory × 2`` retry is a guess.
This module sizes the retry from the run's own trace: it takes the observed peak
resident memory of the failed task (or a same-process sibling that survived) and
scales it by a safety factor. Pure and I/O-free so it is unit-testable without a
run; the wiring into the heal loop (and the ceiling-clamp / never-shrink math)
lives in ``self_heal.apply_patch``.
"""

from __future__ import annotations

import math
from typing import NamedTuple

from contig.models import TaskEvent, TaskResource

# Headroom over the observed peak: an OOM retry sized at exactly the peak would
# race the same wall. 1.5× is the default; code-overridable via the `factor` arg.
PEAK_RSS_SAFETY_FACTOR = 1.5


class PeakSizing(NamedTuple):
    """The sized memory target plus the evidence tier it was derived from.

    `target_gb` is the binary-GB request to retry with (None when unavailable);
    `tier` records which rung of the ladder produced it ("oom_task" | "sibling"
    | "unavailable"); `observed_peak_mb` is the raw peak the size came from.
    """

    target_gb: int | None
    tier: str
    observed_peak_mb: float | None


def peak_informed_memory_gb(
    events: list[TaskEvent],
    usage: list[TaskResource],
    *,
    factor: float = PEAK_RSS_SAFETY_FACTOR,
) -> PeakSizing:
    """Size an OOM memory retry from the observed peak RSS in the trace.

    Fallback ladder (a killed task often reports a `-`/0 peak, so we widen):
      a. the OOM'd task's own peak (join on process+name), else
      b. the max peak of any surviving same-process sibling, else
      c. unavailable — no usable peak, caller falls back to a blind bump.
    A peak of 0 (dash in the trace) is treated as unknown throughout.
    """
    oom_keys = {(e.process, e.name) for e in events if e.exit == 137}
    oom_procs = {e.process for e in events if e.exit == 137}

    # tier a: the OOM'd task's own measured peak.
    exact = [
        r.peak_rss_mb
        for r in usage
        if (r.process, r.name) in oom_keys and r.peak_rss_mb > 0
    ]
    if exact:
        return _sized(max(exact), "oom_task", factor)

    # tier b: a same-process sibling that survived and carries a peak.
    sib = [r.peak_rss_mb for r in usage if r.process in oom_procs and r.peak_rss_mb > 0]
    if sib:
        return _sized(max(sib), "sibling", factor)

    # tier c: no usable observed peak.
    return PeakSizing(None, "unavailable", None)


def _sized(peak_mb: float, tier: str, factor: float) -> PeakSizing:
    """Scale an observed peak (MB) into a binary-GB target with headroom."""
    target_gb = math.ceil(peak_mb / 1024 * factor)
    return PeakSizing(target_gb, tier, peak_mb)
