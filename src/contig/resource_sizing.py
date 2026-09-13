"""Peak-RSS-informed memory sizing for OOM retries (capability C2, self-heal).

When a task is OOM-killed (exit 137), a blind ``memory × 2`` retry is a guess.
This module sizes the retry from the run's own trace: it takes the observed peak
resident memory of the failed task and scales it by a safety factor. Pure and
I/O-free so it is unit-testable without a run; the wiring into the heal loop (and
the ceiling-clamp / never-shrink math) lives in ``self_heal.apply_patch``.

The ladder is deliberately honest and FOUR-tier: (a) the OOM'd task's own
observed peak, else (b) a same-process surviving sibling's peak when the killed
row's own peak is a dash/0 (shipped: the trace parser now carries a coarse
process column, so the sibling key can diverge from the own-task key), else
(c) sibling_dominated when that sibling peak sizes at or below the current
limit — a retry at that size would be a no-op, so the caller falls back to the
blind multiplier, else (d) unavailable, also falling back to blind.
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
    "sibling_peak" | "sibling_dominated" | "unavailable"); `observed_peak_mb` is
    the raw peak the size came from; `source_name` names the row that peak came
    from (None for the own-task tier, whose source is the OOM'd task itself).
    """

    target_gb: int | None
    tier: str
    observed_peak_mb: float | None
    source_name: str | None = None


def peak_informed_memory_gb(
    events: list[TaskEvent],
    usage: list[TaskResource],
    *,
    factor: float = PEAK_RSS_SAFETY_FACTOR,
    current_gb: int | None = None,
) -> PeakSizing:
    """Size an OOM memory retry from the observed peak RSS in the trace.

    Four-tier ladder, honest about what it knows (a killed task often reports a
    `-`/0 peak):
      a. the OOM'd task's own observed peak (join on process+name), else
      b. the same-`process` sibling's peak, sized raw (guard is the caller's),
         else
      c. sibling_dominated — a sibling peak exists but sizes at or below the
         current limit, so a retry at that size would be a no-op; caller falls
         back to a blind bump, else
      d. unavailable — no usable peak anywhere, caller falls back to a blind bump.
    A peak of 0 (dash in the trace) is treated as unknown. The sibling rung
    borrows a surviving sibling's peak when the killed row's own peak is a dash;
    the OOM'd rows have peak 0 by construction, so they cannot leak in.
    """
    oom_keys = {(e.process, e.name) for e in events if e.exit == 137}
    observed = [
        r.peak_rss_mb
        for r in usage
        if (r.process, r.name) in oom_keys and r.peak_rss_mb > 0
    ]
    if not observed:
        oom_processes = {e.process for e in events if e.exit == 137}
        siblings = [
            (r.peak_rss_mb, r.name)
            for r in usage
            if r.process in oom_processes and r.peak_rss_mb > 0
        ]
        if not siblings:
            return PeakSizing(None, "unavailable", None)
        peak, src = max(siblings, key=lambda t: t[0])
        candidate = _sized(peak, factor)
        if current_gb is not None and candidate <= current_gb:
            return PeakSizing(None, "sibling_dominated", peak, src)
        return PeakSizing(candidate, "sibling_peak", peak, src)
    peak = max(observed)
    return PeakSizing(_sized(peak, factor), "oom_task", peak)


def _sized(peak_mb: float, factor: float) -> int:
    """Scale an observed peak (MB) into a binary-GB target with headroom."""
    return math.ceil(peak_mb / 1024 * factor)


# Headroom over the observed walltime: retrying at exactly the observed runtime
# would race the same clock. 1.5× is the default; code-overridable via `factor`.
WALLTIME_SAFETY_FACTOR = 1.5


class TimeSizing(NamedTuple):
    """The sized walltime target plus the evidence tier it was derived from.

    `target_h` is the wall-hour request to retry with (None when unavailable);
    `tier` records which rung produced it ("realtime" | "unavailable");
    `observed_realtime_sec` is the raw longest realtime the size came from.
    """

    target_h: int | None
    tier: str
    observed_realtime_sec: float | None


def realtime_informed_time_h(
    events: list[TaskEvent],
    usage: list[TaskResource],
    *,
    factor: float = WALLTIME_SAFETY_FACTOR,
) -> TimeSizing:
    """Size a walltime retry from the observed realtime in the trace.

    Unlike the memory sizer, a `time_limit` kill has no `exit == 137` join key,
    so this keys on the MAX realtime across all usage rows rather than a specific
    failed task. `events` is kept in the signature only for symmetry with the
    memory sizer; the pure walltime sizer reads `usage` alone. A realtime of 0
    (a dash in the trace) is treated as unknown and excluded by the `> 0` filter.

    Honest two-tier ladder:
      a. longest observed realtime across usage rows, scaled by `factor`, else
      c. unavailable — no usable realtime, caller falls back to a blind bump.

    A `realtime` recorded at a walltime kill is a CENSORED LOWER BOUND (the task
    was killed before finishing), so the floor-at-blind lives in
    ``self_heal.apply_patch``, not here; this helper returns the raw sized target.
    """
    observed = [r.realtime_sec for r in usage if r.realtime_sec > 0]
    if not observed:
        return TimeSizing(None, "unavailable", None)
    longest = max(observed)
    return TimeSizing(math.ceil(longest / 3600 * factor), "realtime", longest)
