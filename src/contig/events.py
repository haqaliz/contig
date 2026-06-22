"""Ingest Nextflow trace files into the frozen TaskEvent / RunSummary contract.

A trace file is the machine-readable, file-based capture of a run, produced by
`nextflow run ... -with-trace trace.txt`. It is a TSV with a header row whose
default columns are:

    task_id  hash  native_id  name  status  exit  submit  duration  realtime

This module reduces each data row to a `contig.models.TaskEvent`, the unit the
failure detector and RunRecord consume.
"""

from __future__ import annotations

import re
from pathlib import Path

from contig.models import RunSummary, TaskEvent, TaskResource

# Duration unit -> seconds. Nextflow writes durations as space-joined parts
# ("1h 4m", "2m 3s", "980ms"); each part is a number plus one of these units.
_DURATION_UNITS = {"ms": 0.001, "s": 1.0, "m": 60.0, "h": 3600.0, "d": 86400.0}
# Size unit -> megabytes. Nextflow writes peak_rss as "1.2 GB", "512 MB", etc.;
# binary multiples (1 GB = 1024 MB), matching Nextflow's MemoryUnit.
_SIZE_UNITS_MB = {"B": 1 / (1 << 20), "KB": 1 / 1024, "MB": 1.0, "GB": 1024.0, "TB": 1024.0 * 1024.0}

_DURATION_PART = re.compile(r"([\d.]+)\s*(ms|s|m|h|d)")
_SIZE = re.compile(r"([\d.]+)\s*([KMGT]?B)", re.IGNORECASE)


def parse_duration_sec(value: str | None) -> float:
    """Parse a Nextflow duration ('2m 3s', '1h 4m', '980ms') into seconds.

    A dash or blank (a task that never ran) is zero, never a guess. Parts are
    summed so multi-unit literals like '1h 4m' resolve correctly.
    """
    if value is None or value.strip() in ("", "-"):
        return 0.0
    total = 0.0
    for amount, unit in _DURATION_PART.findall(value):
        total += float(amount) * _DURATION_UNITS[unit]
    return total


def parse_size_mb(value: str | None) -> float:
    """Parse a Nextflow byte size ('1.2 GB', '512 MB', '2048 KB') into megabytes.

    A dash or blank (no measurement) is zero. Binary multiples, matching how
    Nextflow renders MemoryUnit, so the cost model prices the same number.
    """
    if value is None or value.strip() in ("", "-"):
        return 0.0
    match = _SIZE.match(value.strip())
    if not match:
        return 0.0
    amount, unit = match.group(1), match.group(2).upper()
    return float(amount) * _SIZE_UNITS_MB.get(unit, 0.0)


def parse_pct_cpu(value: str | None) -> float:
    """Parse a Nextflow '%cpu' literal ('180.4%') into a float; dash/blank is zero."""
    if value is None or value.strip() in ("", "-"):
        return 0.0
    return float(value.strip().rstrip("%"))


def parse_trace_text(text: str) -> list[TaskEvent]:
    """Parse a Nextflow trace TSV string into terminal task events.

    Columns are resolved by header NAME, not position: Nextflow's `trace.fields`
    is configurable, and the detector keys on process/exit; a positional parse
    would silently feed it garbage under a non-default column order.
    """
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        return []
    header = lines[0].split("\t")
    col = {name: i for i, name in enumerate(header)}

    def field(fields: list[str], name: str) -> str | None:
        i = col.get(name)
        return fields[i] if i is not None and i < len(fields) else None

    events: list[TaskEvent] = []
    for line in lines[1:]:
        fields = line.split("\t")
        name = field(fields, "name")
        exit_raw = field(fields, "exit")
        events.append(
            TaskEvent(
                process=name or "",
                status=field(fields, "status") or "",
                exit=None if exit_raw in (None, "-", "") else int(exit_raw),
                task_id=field(fields, "task_id"),
                name=name,
            )
        )
    return events


def parse_trace_file(path: str | Path) -> list[TaskEvent]:
    """Read a Nextflow trace file and parse it into terminal task events."""
    return parse_trace_text(Path(path).read_text())


def parse_resource_usage_text(text: str) -> list[TaskResource]:
    """Parse a trace TSV string into per-task resource actuals.

    Columns are resolved by header NAME (realtime, peak_rss, %cpu, name), so a
    non-default trace.fields order is handled. Each measurement is parsed from
    Nextflow's human format; a missing field (a dash, for a task that never ran)
    is zero, never a fabricated number.
    """
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        return []
    header = lines[0].split("\t")
    col = {name: i for i, name in enumerate(header)}

    def field(fields: list[str], name: str) -> str | None:
        i = col.get(name)
        return fields[i] if i is not None and i < len(fields) else None

    usage: list[TaskResource] = []
    for line in lines[1:]:
        fields = line.split("\t")
        name = field(fields, "name")
        usage.append(
            TaskResource(
                process=name or "",
                name=name,
                realtime_sec=parse_duration_sec(field(fields, "realtime")),
                peak_rss_mb=parse_size_mb(field(fields, "peak_rss")),
                pct_cpu=parse_pct_cpu(field(fields, "%cpu")),
            )
        )
    return usage


def parse_resource_usage_file(path: str | Path) -> list[TaskResource]:
    """Read a Nextflow trace file and parse it into per-task resource actuals."""
    return parse_resource_usage_text(Path(path).read_text())


def summarize_trace_text(text: str) -> RunSummary:
    """Parse a trace TSV string and reduce it to a RunSummary."""
    return RunSummary.from_events(parse_trace_text(text))
