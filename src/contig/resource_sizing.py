"""Peak-RSS-informed memory sizing for OOM retries (capability C2, self-heal).

When a task is OOM-killed (exit 137), a blind ``memory × 2`` retry is a guess.
This module sizes the retry from the run's own trace: it takes the observed peak
resident memory of the failed task and scales it by a safety factor. Pure and
I/O-free so it is unit-testable without a run; the wiring into the heal loop (and
the ceiling-clamp / never-shrink math) lives in ``self_heal.apply_patch``.

The ladder is deliberately honest and TWO-tier: (a) the OOM'd task's own observed
peak, else (c) unavailable, so the caller falls back to the blind multiplier. A
same-process sibling rescue (borrowing a surviving sibling's peak when the killed
row's own peak is a dash/0) is a deferred follow-on: it needs a coarse process
column in the trace parser (today ``process == name`` for every row, so a sibling
key can never diverge from the own-task key and the tier could never fire).
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
    `tier` records which rung of the ladder produced it ("oom_task" |
    "unavailable"); `observed_peak_mb` is the raw peak the size came from.
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

    Honest two-tier ladder (a killed task often reports a `-`/0 peak):
      a. the OOM'd task's own observed peak (join on process+name), else
      c. unavailable — no usable peak, caller falls back to a blind bump.
    A peak of 0 (dash in the trace) is treated as unknown. Same-process sibling
    rescue is a deferred follow-on (needs a coarse process column in the trace
    parser; today process == name, so a sibling key never diverges).
    """
    oom_keys = {(e.process, e.name) for e in events if e.exit == 137}
    observed = [
        r.peak_rss_mb
        for r in usage
        if (r.process, r.name) in oom_keys and r.peak_rss_mb > 0
    ]
    if not observed:
        return PeakSizing(None, "unavailable", None)
    peak = max(observed)
    return PeakSizing(_sized(peak, factor), "oom_task", peak)


def _sized(peak_mb: float, factor: float) -> int:
    """Scale an observed peak (MB) into a binary-GB target with headroom."""
    return math.ceil(peak_mb / 1024 * factor)
