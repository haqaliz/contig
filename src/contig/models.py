"""Core domain contracts for Contig's Layer-2 engine.

These models are the frozen interface every other module imports: the execution
target (where/how a run happens), the QC verdict, the Nextflow events ingested
from a run, and the reproducible RunRecord that ties it all together.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


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
# Run-level verdict adds "unverified": the run completed but no QC check covered
# it, so we must not claim it is verified (PRODUCT_SPEC: false-pass rate ~0).
Verdict = Literal["pass", "warn", "fail", "unverified"]


class QCResult(BaseModel):
    """One verification check's outcome (ARCHITECTURE §6)."""

    check: str
    status: QCStatus
    message: str
    value: float | None = None
    expected_range: str | None = None


def overall_verdict(results: list[QCResult]) -> QCStatus:
    """Reduce QC results to a single verdict; a fail dominates a warn, a warn a pass.

    Refuses an empty list: "all of nothing passed" is the false-pass we must never
    emit (PRODUCT_SPEC). Callers with no checks should report "unverified" instead.
    """
    if not results:
        raise ValueError("overall_verdict requires at least one QC result; use 'unverified'")
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


# --- Self-healing loop (ARCHITECTURE §5) ---------------------------------------

FailureClass = Literal[
    "oom",
    "time_limit",
    "missing_reference",
    "missing_index",
    "bad_param",
    "container_pull_failed",
    "container_unavailable",
    "conda_solve_failed",
    "tool_crash",
    "no_progress",
    "qc_anomaly",
    "unknown",
]


class Diagnosis(BaseModel):
    """A structured root-cause hypothesis for a failed run (ARCHITECTURE §5.2)."""

    failure_class: FailureClass
    root_cause: str
    evidence: list[str] = []
    confidence: float = Field(ge=0.0, le=1.0)


class Patch(BaseModel):
    """A typed, machine-applicable candidate fix (ARCHITECTURE §5.3).

    Never free-text: the operation is a structured change, and `risk` gates
    whether it auto-applies. `expected_signal` is how DETECT confirms it worked.
    """

    kind: Literal["param", "resource", "env", "reference", "retry", "code"]
    operation: dict[str, object]
    rationale: str
    risk: Literal["safe", "needs_confirmation", "destructive"]
    expected_signal: str


class RepairStep(BaseModel):
    """One detect→diagnose→patch→outcome transition in the repair history."""

    attempt: int
    diagnosis: Diagnosis
    patch: Patch | None = None
    outcome: str


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
    repair_history: list[RepairStep] = []

    @property
    def verdict(self) -> Verdict:
        """Conservative, honest verdict (ARCHITECTURE §6; PRODUCT_SPEC trust model).

        A run that did not complete cannot be trusted regardless of QC; a run with
        no QC coverage is "unverified", never "pass".
        """
        if not RunSummary.from_events(self.events).succeeded:
            return "fail"
        if not self.qc_results:
            return "unverified"
        return overall_verdict(self.qc_results)
