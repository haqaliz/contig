"""Ingest Nextflow trace files into the frozen TaskEvent / RunSummary contract.

A trace file is the machine-readable, file-based capture of a run, produced by
`nextflow run ... -with-trace trace.txt`. It is a TSV with a header row whose
default columns are:

    task_id  hash  native_id  name  status  exit  submit  duration  realtime

This module reduces each data row to a `contig.models.TaskEvent`, the unit the
failure detector and RunRecord consume.
"""

from __future__ import annotations

from pathlib import Path

from contig.models import RunSummary, TaskEvent


def parse_trace_text(text: str) -> list[TaskEvent]:
    """Parse a Nextflow trace TSV string into terminal task events.

    Columns are resolved by header NAME, not position: Nextflow's `trace.fields`
    is configurable, and the detector keys on process/exit - a positional parse
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


def summarize_trace_text(text: str) -> RunSummary:
    """Parse a trace TSV string and reduce it to a RunSummary."""
    return RunSummary.from_events(parse_trace_text(text))
