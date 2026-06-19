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
    """Parse a Nextflow trace TSV string into terminal task events."""
    events: list[TaskEvent] = []
    for line in text.splitlines()[1:]:
        if not line.strip():
            continue
        fields = line.split("\t")
        events.append(
            TaskEvent(
                process=fields[3],
                status=fields[4],
                exit=None if fields[5] == "-" else int(fields[5]),
                task_id=fields[0],
                name=fields[3],
            )
        )
    return events


def parse_trace_file(path: str | Path) -> list[TaskEvent]:
    """Read a Nextflow trace file and parse it into terminal task events."""
    return parse_trace_text(Path(path).read_text())


def summarize_trace_text(text: str) -> RunSummary:
    """Parse a trace TSV string and reduce it to a RunSummary."""
    return RunSummary.from_events(parse_trace_text(text))
