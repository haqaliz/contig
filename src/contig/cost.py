"""Price a run's measured resource usage against configurable rates (PRD contract B).

Local runs are free, so the rates default to 0. On managed compute a per-task
cost is the realtime priced as cpu-hours plus the peak memory priced as GB-hours;
the report sums these into a run total. This is deliberately a thin, auditable
model: the inputs are the recorded actuals, never an estimate.
"""

from __future__ import annotations

from contig.models import TaskResource

_SECONDS_PER_HOUR = 3600.0
_MB_PER_GB = 1024.0


def task_cost(
    task: TaskResource, *, rate_cpu_hour: float, rate_mem_gb_hour: float
) -> float:
    """Cost of one task: realtime as cpu-hours plus peak memory as GB-hours."""
    cpu_hours = task.realtime_sec / _SECONDS_PER_HOUR
    gb_hours = (task.peak_rss_mb / _MB_PER_GB) * (task.realtime_sec / _SECONDS_PER_HOUR)
    return cpu_hours * rate_cpu_hour + gb_hours * rate_mem_gb_hour


def cost_report(
    usage: list[TaskResource],
    *,
    rate_cpu_hour: float = 0.0,
    rate_mem_gb_hour: float = 0.0,
    currency: str = "USD",
) -> dict:
    """Price every task and the run total against the given rates.

    The shape is pinned (PRD contract B): {currency, rate_cpu_hour,
    rate_mem_gb_hour, total, by_task: [{name, realtime_sec, peak_rss_mb, cost}]}.
    Empty usage reports a zero total and an empty by_task: a run with no recorded
    resource actuals has nothing to price.
    """
    by_task = []
    total = 0.0
    for task in usage:
        cost = task_cost(
            task, rate_cpu_hour=rate_cpu_hour, rate_mem_gb_hour=rate_mem_gb_hour
        )
        total += cost
        by_task.append(
            {
                "name": task.name,
                "realtime_sec": task.realtime_sec,
                "peak_rss_mb": task.peak_rss_mb,
                "cost": cost,
            }
        )
    return {
        "currency": currency,
        "rate_cpu_hour": rate_cpu_hour,
        "rate_mem_gb_hour": rate_mem_gb_hour,
        "total": total,
        "by_task": by_task,
    }
