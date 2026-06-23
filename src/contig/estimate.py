"""Pre-run estimate: project a run's cost before it launches (PRD contract B).

Data-driven first: scan the runs directory for prior FINISHED runs of the same
pipeline, derive a per-sample runtime and cpu-hour figure from their recorded
resource_usage and sample counts, and scale to the requested sample count. When
there is no usable history, fall back to a transparent per-sample heuristic so
the estimate is always honest about its basis. The cost figure reuses the same
cpu-hour / GB-hour model that contig.cost prices actuals with.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel

from contig.models import RunRecord, RunSummary, TaskResource
from contig.samplesheet import parse_samplesheet
from contig.workspace import list_run_ids, load_run

_SECONDS_PER_HOUR = 3600.0
_MB_PER_GB = 1024.0

# Transparent per-sample heuristic used when there is no history to learn from.
# Deliberately modest, round numbers a user can sanity-check: roughly ten minutes
# and two GB of peak memory per sample. The estimate's `note` says it is a guess.
_HEURISTIC_RUNTIME_SEC_PER_SAMPLE = 600.0
_HEURISTIC_PEAK_MEM_MB = 2048.0


class EstimateReport(BaseModel):
    """A projected run cost, with its basis (history or heuristic) made explicit.

    The shape is pinned (PRD contract B) so the dashboard renders it directly:
    runtime and peak memory are projected totals, est_total_cpu_hours and est_cost
    drive the priced figure, and `note` explains how the estimate was derived.
    """

    basis: str  # "history" | "heuristic"
    pipeline: str
    n_samples: int
    n_prior_runs: int
    est_runtime_sec: float
    est_peak_mem_mb: float
    est_total_cpu_hours: float
    est_cost: float
    currency: str
    rate_cpu_hour: float
    rate_mem_gb_hour: float
    note: str


def _sample_count(record: RunRecord) -> int | None:
    """The prior run's sample count from its recorded sample sheet, or None.

    A run records its absolutized sheet path in parameters["input"]; we count the
    rows there. A run with no recorded sheet (the bundled test profile), or one
    whose sheet has moved or no longer parses, yields None so it is skipped as a
    per-sample data point rather than guessed at.
    """
    sheet = record.parameters.get("input")
    if not sheet:
        return None
    path = Path(str(sheet))
    if not path.exists():
        return None
    try:
        rows = parse_samplesheet(path)
    except (ValueError, OSError):
        return None
    return len(rows) or None


def _per_sample_history(pipeline: str, runs_dir: str | Path) -> list[tuple[float, float]]:
    """Per-sample (runtime_sec, cpu_hours) and peak_mem for each usable prior run.

    A prior run is usable when it is the SAME pipeline, FINISHED (every task
    succeeded), carries recorded resource_usage, and has a reachable sample sheet
    to divide by. Returns one (runtime_per_sample, peak_mem_mb) pair per such run.
    """
    points: list[tuple[float, float]] = []
    for run_id in list_run_ids(runs_dir):
        try:
            record = load_run(runs_dir, run_id)
        except Exception:
            continue
        if record.pipeline != pipeline:
            continue
        if not RunSummary.from_events(record.events).succeeded:
            continue
        if not record.resource_usage:
            continue
        n = _sample_count(record)
        if not n:
            continue
        total_runtime = sum(t.realtime_sec for t in record.resource_usage)
        peak_mem = _peak_mem(record.resource_usage)
        points.append((total_runtime / n, peak_mem))
    return points


def _peak_mem(usage: list[TaskResource]) -> float:
    """The single heaviest task's peak resident memory (the run's memory ceiling)."""
    return max((t.peak_rss_mb for t in usage), default=0.0)


def estimate_run(
    pipeline: str,
    n_samples: int,
    runs_dir: str | Path,
    *,
    rate_cpu_hour: float = 0.0,
    rate_mem_gb_hour: float = 0.0,
    currency: str = "USD",
) -> EstimateReport:
    """Estimate a run's runtime, peak memory, cpu-hours, and cost before launch.

    History-driven when prior FINISHED runs of this pipeline exist (their per-sample
    runtime averaged and scaled to n_samples; peak memory is the largest observed,
    since memory is a ceiling, not a per-sample sum); otherwise a transparent
    per-sample heuristic. The cost reuses the cpu-hour / GB-hour rates.
    """
    if n_samples <= 0:
        raise ValueError(f"n_samples must be positive, got {n_samples}")

    points = _per_sample_history(pipeline, runs_dir)
    if points:
        basis = "history"
        n_prior_runs = len(points)
        runtime_per_sample = sum(p[0] for p in points) / len(points)
        est_runtime_sec = runtime_per_sample * n_samples
        est_peak_mem_mb = max(p[1] for p in points)
        note = (
            f"estimated from {n_prior_runs} prior finished run(s) of {pipeline}, "
            f"scaled to {n_samples} sample(s)"
        )
    else:
        basis = "heuristic"
        n_prior_runs = 0
        est_runtime_sec = _HEURISTIC_RUNTIME_SEC_PER_SAMPLE * n_samples
        est_peak_mem_mb = _HEURISTIC_PEAK_MEM_MB
        note = (
            f"no prior {pipeline} runs; a per-sample heuristic of "
            f"{_HEURISTIC_RUNTIME_SEC_PER_SAMPLE:.0f}s and "
            f"{_HEURISTIC_PEAK_MEM_MB:.0f} MB per sample"
        )

    est_total_cpu_hours = est_runtime_sec / _SECONDS_PER_HOUR
    gb_hours = (est_peak_mem_mb / _MB_PER_GB) * est_total_cpu_hours
    est_cost = est_total_cpu_hours * rate_cpu_hour + gb_hours * rate_mem_gb_hour

    return EstimateReport(
        basis=basis,
        pipeline=pipeline,
        n_samples=n_samples,
        n_prior_runs=n_prior_runs,
        est_runtime_sec=est_runtime_sec,
        est_peak_mem_mb=est_peak_mem_mb,
        est_total_cpu_hours=est_total_cpu_hours,
        est_cost=est_cost,
        currency=currency,
        rate_cpu_hour=rate_cpu_hour,
        rate_mem_gb_hour=rate_mem_gb_hour,
        note=note,
    )
