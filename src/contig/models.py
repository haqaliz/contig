"""Core domain contracts for Contig's Layer-2 engine.

These models are the frozen interface every other module imports: the execution
target (where/how a run happens), the QC verdict, the Nextflow events ingested
from a run, and the reproducible RunRecord that ties it all together.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, computed_field


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
    # Backend-specific knobs (e.g. AWS Batch queue/region) the mapping layer
    # needs but that don't generalize across backends. Kept generic so the
    # agent never special-cases the backend (ARCHITECTURE §4.1).
    backend_options: dict[str, str] = Field(default_factory=dict)
    # Per-process resource ceilings (memory/cpus/time) emitted as Nextflow's
    # `process.resourceLimits`. This is the modern knob: nf-core dropped the old
    # `--max_memory`/`--max_cpus` params, so caps must ride in the config.
    resource_limits: dict[str, str] = Field(default_factory=dict)


# A single check's status. "unverified" means the check ran but could not
# corroborate anything (e.g. concordance over two call sets that share no
# comparable site): it must never be read as a pass (PRODUCT_SPEC: false-pass
# rate ~0). It carries no severity, so it neither passes nor fails a verdict.
QCStatus = Literal["pass", "warn", "fail", "unverified"]
# Run-level verdict: same vocabulary; "unverified" is the run-level verdict when
# no QC check covered the run at all.
Verdict = Literal["pass", "warn", "fail", "unverified"]
# What kind of check produced a result: a content-level metric check (rule pack on
# MultiQC metrics), a structural/integrity check on the output files themselves, or
# a cross-tool concordance check (agreement between two independent call sets).
# Lets the dashboard group them; defaults to "metric" so older records that
# predate the field deserialize unchanged.
QCKind = Literal["metric", "structural", "concordance"]


class QCResult(BaseModel):
    """One verification check's outcome (ARCHITECTURE §6)."""

    check: str
    status: QCStatus
    message: str
    value: float | None = None
    expected_range: str | None = None
    kind: QCKind = "metric"


def overall_verdict(results: list[QCResult]) -> QCStatus:
    """Reduce QC results to a single verdict; a fail dominates a warn, a warn a pass.

    Refuses an empty list: "all of nothing passed" is the false-pass we must never
    emit (PRODUCT_SPEC). Callers with no checks should report "unverified" instead.
    An "unverified" check carries no severity (it corroborated nothing); it cannot
    by itself turn into a pass, so a set of only unverified checks reduces to
    "unverified", never "pass".
    """
    if not results:
        raise ValueError("overall_verdict requires at least one QC result; use 'unverified'")
    statuses = {r.status for r in results}
    if "fail" in statuses:
        return "fail"
    if "warn" in statuses:
        return "warn"
    if "pass" in statuses:
        return "pass"
    return "unverified"


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


class TaskResource(BaseModel):
    """One task's measured resource usage, parsed from the Nextflow trace.

    realtime_sec is wall-clock seconds, peak_rss_mb is peak resident memory in
    megabytes, pct_cpu is the trace's %cpu (can exceed 100 on multi-core tasks).
    These are the actuals the cost model prices and the dashboard shows.
    """

    process: str
    name: str | None = None
    realtime_sec: float
    peak_rss_mb: float
    pct_cpu: float


class RunSummary(BaseModel):
    """The reduced outcome of a run, derived from its terminal task events."""

    total_tasks: int
    failed_tasks: int
    succeeded: bool

    @classmethod
    def from_events(cls, events: list[TaskEvent]) -> RunSummary:
        failed = sum(1 for e in events if e.is_failure)
        return cls(total_tasks=len(events), failed_tasks=failed, succeeded=failed == 0)


# --- Planning / intake (ARCHITECTURE §P4) --------------------------------------
# A thin layer that maps a goal + data shape to a CURATED pipeline and proposes
# params for the user to approve. The NL→assay step is a replaceable provider -
# the moat is the curated registry + the run/verify engine, not the prompting.


class PipelineEntry(BaseModel):
    """One curated pipeline in the registry: which pipeline serves which assay."""

    assay: str
    pipeline: str
    revision: str
    description: str


class DataShape(BaseModel):
    """What the input data looks like, inferred from the sample sheet."""

    n_samples: int
    layout: Literal["paired", "single", "mixed"]
    warnings: list[str] = []


class Plan(BaseModel):
    """A proposed, human-readable analysis plan to approve before running."""

    assay: str
    pipeline: str
    revision: str
    params: dict[str, object] = {}
    rationale: str
    warnings: list[str] = []


# --- Reference identity (ARCHITECTURE §7; capability C5 slice 1) ---------------
# Captures which reference genome a run used so provenance records are fully
# reproducible. This is capture-only: no mismatch detection, no version
# resolution, no known-sites — those belong to later slices.


class ReferenceIdentity(BaseModel):
    """The reference genome a run consumed, for provenance capture."""

    mode: Literal["igenomes", "explicit"]
    genome: str | None = None              # iGenomes key (mode == "igenomes")
    fasta: str | None = None               # reference path (mode == "explicit")
    gtf: str | None = None
    fasta_sha256: str | None = None        # None when unavailable
    gtf_sha256: str | None = None
    annotation_version: str | None = None  # null this slice (no fabrication)


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
    "platform_unsupported",
    "disk_full",
    "download_failed",
    "permission_denied",
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
    detail: str | None = None


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
    resource_usage: list[TaskResource] = []
    reference_identity: ReferenceIdentity | None = None

    @computed_field  # serialized into run_record.json so the dashboard reads it directly
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


# --- Reproduce manifest (one-click reproduce; PRD contract A) -------------------
# The launch sidecar that makes every run reproducible: it captures the full
# `contig run` invocation BEFORE the run starts, so it exists during the run and
# on early failure. Reproduce rebuilds the argv from this with a fresh run_id and
# a re-defaulted outdir/work_dir (so those are deliberately NOT stored here).


class LaunchManifest(BaseModel):
    """The captured `contig run` invocation, serialized to runs/<id>/launch.json.

    `is_test_profile` is derived (input is None means the bundled test profile
    ran). outdir/work_dir are intentionally absent: reproduce re-defaults them
    under the new run dir.
    """

    run_id: str
    pipeline: str
    revision: str
    profiles: list[str]
    backend: str
    container_runtime: str
    input: str | None = None
    genome: str | None = None
    fasta: str | None = None
    gtf: str | None = None
    max_memory: str | None = None
    max_cpus: int | None = None
    max_attempts: int = 3
    # Whether the disjoint FASTA/GTF pre-flight gate was overridden for this run.
    # Persisted so a reproduce (`rerun`) is faithful to the original's intent;
    # defaults False so a legacy launch.json (written before this field) stays valid.
    allow_reference_mismatch: bool = False
    created_at: str

    @computed_field  # serialized so the dashboard reads it without re-deriving
    @property
    def is_test_profile(self) -> bool:
        return self.input is None


# --- Failure corpus + detector eval (moat #2: accumulated evaluation data) ------
# A labeled record of a real (or synthetic) failure, carrying exactly what the
# detector consumes, so the eval can replay diagnose_failure over it and score
# the detector. The corpus compounds as real runs accrue.


class FailureCase(BaseModel):
    """One labeled failure: detector inputs (events + log) plus the true class."""

    case_id: str
    description: str
    source: str  # provenance: a run id, or "synthetic"
    events: list[TaskEvent] = []
    log_text: str = ""
    expected_class: FailureClass


class DetectorMismatch(BaseModel):
    """A case the detector got wrong: what it should have said vs what it did."""

    case_id: str
    expected: FailureClass
    predicted: FailureClass


class ClassScore(BaseModel):
    """Per-class precision/recall over the corpus."""

    support: int  # cases whose true class is this
    predicted: int  # cases the detector assigned this class
    correct: int  # true positives
    precision: float
    recall: float


class DetectorEvalReport(BaseModel):
    """The result of replaying the detector over a failure corpus."""

    total: int
    correct: int
    accuracy: float
    mismatches: list[DetectorMismatch] = []
    per_class: dict[str, ClassScore] = {}


class EvalSnapshot(BaseModel):
    """One detector-eval result tied to a corpus version (PRD contract D).

    Appended to a committed JSONL history so detector accuracy over time is
    auditable and the dashboard can render the trend. `corpus_sha` ties the
    snapshot to the exact corpus file it scored.
    """

    timestamp: str
    corpus_size: int
    corpus_sha: str
    accuracy: float
    per_class: dict[str, ClassScore] = {}
    contig_version: str | None = None
    # Which detector produced this snapshot, so the trend can compare detectors
    # (e.g. rules vs llm) on the same corpus. Defaults to the deterministic rules
    # detector for back-compat with snapshots written before detectors were named.
    detector: str = "rules"
