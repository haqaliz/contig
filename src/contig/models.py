"""Core domain contracts for Contig's Layer-2 engine.

These models are the frozen interface every other module imports: the execution
target (where/how a run happens), the QC verdict, the Nextflow events ingested
from a run, and the reproducible RunRecord that ties it all together.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel


def sha256_file(path: str | Path, chunk_size: int = 1 << 20) -> str:
    """Content hash of a file, streamed so large reads/references stay cheap."""
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()

Backend = Literal["local", "aws_batch", "gcp_batch", "slurm", "k8s"]
Engine = Literal["nextflow", "snakemake", "wdl"]
ContainerRuntime = Literal["docker", "singularity", "conda"]


class ExecutionTarget(BaseModel):
    """Describes where and how a run executes (ARCHITECTURE §4.1).

    The agent never special-cases the backend; this is the single mapping point.
    """

    backend: Backend
    container_runtime: ContainerRuntime
    work_dir: str
    engine: Engine = "nextflow"
    credentials_ref: str | None = None


QCStatus = Literal["pass", "warn", "fail"]


class QCResult(BaseModel):
    """One verification check's outcome (ARCHITECTURE §6)."""

    check: str
    status: QCStatus
    message: str
    value: float | None = None
    expected_range: str | None = None


def overall_verdict(results: list[QCResult]) -> QCStatus:
    """Reduce QC results to a single verdict; a fail dominates a warn, a warn a pass."""
    statuses = {r.status for r in results}
    if "fail" in statuses:
        return "fail"
    if "warn" in statuses:
        return "warn"
    return "pass"


class TaskEvent(BaseModel):
    """One terminal task state captured from a Nextflow run.

    Ingestion is responsible for emitting a single terminal event per task
    (dedup raw `-with-weblog` lines, keep the last). This is the unit the
    failure detector (ARCHITECTURE §5.1) and the RunRecord consume.
    """

    process: str
    status: str
    exit: int | None = None
    task_id: str | None = None
    name: str | None = None

    @property
    def is_failure(self) -> bool:
        return self.status.upper() == "FAILED" or (self.exit is not None and self.exit != 0)


class RunSummary(BaseModel):
    """The reduced outcome of a run, derived from its terminal task events."""

    total_tasks: int
    failed_tasks: int
    succeeded: bool

    @classmethod
    def from_events(cls, events: list[TaskEvent]) -> RunSummary:
        failed = sum(1 for e in events if e.is_failure)
        return cls(total_tasks=len(events), failed_tasks=failed, succeeded=failed == 0)


class RunRecord(BaseModel):
    """The complete, re-runnable record of a run (ARCHITECTURE §7).

    "A run is re-runnable iff a stranger, given only its provenance record, can
    reproduce the result." Captured continuously, not reconstructed after.
    """

    run_id: str
    pipeline: str
    pipeline_revision: str
    target: ExecutionTarget
    input_checksums: dict[str, str]
    parameters: dict[str, object] = {}
    container_digests: dict[str, str] = {}
    nextflow_version: str | None = None
    contig_version: str | None = None
    events: list[TaskEvent] = []
    qc_results: list[QCResult] = []
    output_checksums: dict[str, str] = {}

    @property
    def verdict(self) -> QCStatus:
        return overall_verdict(self.qc_results)
