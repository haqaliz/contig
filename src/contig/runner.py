"""Drives the workflow manager in the data plane (ARCHITECTURE §3, §4.2).

For the P0 spike this is just the command builder: it turns a job spec into the
exact Nextflow argv, wiring `-with-trace` so the run is machine-readable and
captured (feeds contig.events ingestion). Actual subprocess execution + RunRecord
assembly is layered on once the toolchain (Nextflow/Docker) is present.
"""

from __future__ import annotations

import subprocess
from importlib.metadata import version as _pkg_version
from pathlib import Path
from typing import Callable

from contig.bundle import compute_input_checksums, write_bundle
from contig.events import parse_trace_file
from contig.models import ExecutionTarget, RunRecord

# An executor runs the Nextflow argv and is responsible for the trace file
# existing at trace_path when it returns. The default shells out; tests inject a
# fake that writes a canned trace, so the parse/assemble/bundle path stays real.
Executor = Callable[[list[str], Path], int]


class PipelineExecutionError(RuntimeError):
    """Raised when the workflow manager exits nonzero (DETECT, ARCHITECTURE §5.1).

    Surfacing the return code cleanly is the entry point for diagnosis/self-heal;
    it must not be masked by a downstream missing-trace traceback.
    """

    def __init__(self, returncode: int):
        self.returncode = returncode
        super().__init__(f"Nextflow exited with code {returncode}")


def default_executor(cmd: list[str], trace_path: Path) -> int:
    """Run the Nextflow command as a subprocess in the data plane."""
    return subprocess.run(cmd, cwd=trace_path.parent, check=False).returncode


def build_nextflow_command(
    pipeline: str,
    revision: str,
    profiles: list[str],
    trace_path: str,
    params: dict[str, object] | None = None,
) -> list[str]:
    """Construct the `nextflow run` argv for a pipeline, with trace capture wired in."""
    cmd = [
        "nextflow",
        "run",
        pipeline,
        "-r",
        revision,
        "-profile",
        ",".join(profiles),
        "-with-trace",
        trace_path,
    ]
    for key, value in (params or {}).items():
        cmd += [f"--{key}", str(value)]
    return cmd


def run_pipeline(
    *,
    pipeline: str,
    revision: str,
    profiles: list[str],
    target: ExecutionTarget,
    input_paths: list[str | Path],
    runs_dir: str | Path,
    run_id: str,
    executor: Executor = default_executor,
    params: dict[str, object] | None = None,
    nextflow_version: str | None = None,
) -> RunRecord:
    """Run a pipeline and capture it into a reproducible, bundled RunRecord.

    Ties the spike together: build the command, execute it (writing a trace),
    ingest the trace into events, assemble the provenance record, and persist a
    portable reproduce-bundle. The result is a run we can prove and re-run.
    """
    run_dir = (Path(runs_dir) / run_id).resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    trace_path = run_dir / "trace.txt"

    cmd = build_nextflow_command(pipeline, revision, profiles, str(trace_path), params)
    returncode = executor(cmd, trace_path)
    if returncode != 0:
        raise PipelineExecutionError(returncode)

    events = parse_trace_file(trace_path)
    record = RunRecord(
        run_id=run_id,
        pipeline=pipeline,
        pipeline_revision=revision,
        target=target,
        input_checksums=compute_input_checksums(input_paths),
        parameters=params or {},
        events=events,
        nextflow_version=nextflow_version,
        contig_version=_pkg_version("contig"),
    )
    write_bundle(record, run_dir)
    return record
