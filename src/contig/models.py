"""Core domain contracts for Contig's Layer-2 engine.

These models are the frozen interface every other module imports: the execution
target (where/how a run happens), the QC verdict, the Nextflow events ingested
from a run, and the reproducible RunRecord that ties it all together.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, computed_field, field_validator


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
    # Whether this check asserts anything at all (has a warn/fail band) vs. is
    # purely observational (e.g. a metric surfaced with no pass/fail bounds).
    # Defaults to False so records predating the field deserialize unchanged.
    # Orthogonal to `kind`: an informational check is still `kind="metric"`;
    # `kind` says what produced the result, `informational` says whether it
    # asserts anything.
    informational: bool = False


def overall_verdict(results: list[QCResult]) -> QCStatus:
    """Reduce QC results to a single verdict; a fail dominates a warn, a warn a pass.

    Refuses an empty list: "all of nothing passed" is the false-pass we must never
    emit (PRODUCT_SPEC). Callers with no checks should report "unverified" instead.
    An "unverified" check carries no severity (it corroborated nothing); it cannot
    by itself turn into a pass, so a set of only unverified checks reduces to
    "unverified", never "pass".

    An `informational` check likewise carries no severity, whatever its `status`:
    it asserts nothing, so it can never contribute a pass (or a warn/fail) to the
    verdict. The empty-list guard above runs on the full, unfiltered list — an
    all-informational list is not empty and must not raise; it just has no
    severity-bearing result to reduce over. So: a result set containing only
    informational and/or unverified checks reduces to "unverified", never "pass".
    """
    if not results:
        raise ValueError("overall_verdict requires at least one QC result; use 'unverified'")
    severe = [r for r in results if not r.informational]
    statuses = {r.status for r in severe}
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
    # Declarative per-assay Nextflow params merged into a run's params at dispatch
    # (without overriding user-supplied values). Empty for most assays; somatic
    # sarek uses it to inject `--tools strelka,mutect2` so the run genuinely
    # invokes the somatic callers. default_factory=dict avoids a shared mutable
    # default across entries.
    default_params: dict[str, object] = Field(default_factory=dict)


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
    harmonized: bool = False
    harmonized_direction: str | None = None


class AnnotationProvenance(BaseModel):
    """Which annotation tool + DB version a run's annotated VCF was produced by.

    Parsed from the annotated VCF's own header (the tool records its version there),
    captured for provenance. Research-use attribution only — this records WHAT tool
    and DB reported, never a significance judgement.
    """

    tool: Literal["VEP", "SnpEff"]
    version: str | None = None
    # The annotation cache/build identifier the tool ran against (VEP cache basename
    # e.g. "110_GRCh38"; SnpEff genome DB e.g. "GRCh38.105"). This is the cache/build
    # release, NOT a per-database (ClinVar/gnomAD) version -- never over-claim it as
    # a "database version". None when the header carries no such token (never
    # fabricated). Optional/defaulted so pre-M5 bundles still load.
    db_version: str | None = None
    raw_header: str | None = None


class SexInference(BaseModel):
    """The germline karyotypic-sex signal (PRD germline-sex-check-plausibility),
    captured as provenance on the RunRecord.

    A serializable mirror of the verification-layer `SexSignals` dataclass
    (`contig.verification.sex_plausibility.SexSignals`) -- this model exists so
    the inference round-trips through the bundle; the compute itself lives in
    the verification layer. Research-use inference only, never a clinical
    determination: `inferred_sex` is one of "XY" | "XX" | "discordant" |
    "indeterminate" (never fabricated when the signal is too weak to call).
    """

    inferred_sex: str
    x_het_ratio: float | None = None
    x_sites: int = 0
    y_variant_count: int = 0
    par_masked: bool = False
    reference_build: str | None = None


# --- Self-healing loop (ARCHITECTURE §5) ---------------------------------------

FailureClass = Literal[
    "oom",
    "time_limit",
    "missing_reference",
    "missing_index",
    "reference_not_bgzf",
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
    # M4 enables BOTH VEP and SnpEff on the variant assays, so provenance is a
    # list (one entry per distinct annotator found). Pre-M4 bundles serialized
    # this field as a SINGLE object -- the validator below normalizes that
    # legacy shape (and a bare None) into a list so old bundles still load.
    annotation_identity: list[AnnotationProvenance] = Field(default_factory=list)
    harmonized_reference_direction: str | None = None
    # The resolved assay this run was executed as. Persisted so methods/benchmark
    # can read it directly instead of re-deriving from the pipeline string (which
    # is ambiguous when two assays share a pipeline, e.g. somatic vs germline
    # sarek). Optional/defaulted so legacy bundles written before this field still
    # load and fall back to the pipeline-derived assay.
    assay: str | None = None
    # Germline karyotypic-sex inference, captured at finalize for variant_calling
    # runs only (see self_heal._finalize). Optional/defaulted so pre-slice
    # bundles simply lack the key and load with None -- no validator needed,
    # mirroring ReferenceIdentity's back-compat idiom.
    sex_inference: SexInference | None = None

    @field_validator("annotation_identity", mode="before")
    @classmethod
    def _normalize_annotation_identity(cls, value: object) -> object:
        """Back-compat load-time guarantee for pre-M4 bundles (PRD contract B).

        Pre-M4 serialized `annotation_identity` as a single object (dict or
        AnnotationProvenance); M4 stores a list of them. Normalize here so
        old bundles still deserialize, verify, and reproduce: None -> [],
        a single object -> a one-element list, an existing list -> unchanged.
        """
        if value is None:
            return []
        if isinstance(value, list):
            return value
        return [value]

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
    harmonized_reference: bool = False
    # The resolved assay used for this run (e.g. "somatic_variant_calling"), so a
    # reproduce (`rerun`) re-applies the same assay rather than re-deriving it from
    # the pipeline string. Defaults None so a legacy launch.json (written before
    # this field) stays valid and falls back to the pipeline-derived assay.
    assay: str | None = None
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


class HoldoutGuardResult(BaseModel):
    """The result of scoring a detector against the frozen held-out set and
    comparing it to a committed baseline (C6 slice 1: the regression guard).

    Pinning `holdout_sha`/`baseline_sha` and the two detector names lets the
    guard tell "accuracy dropped" apart from "the held-out set or detector
    changed underneath the comparison" (`sha_mismatch`/`detector_mismatch`),
    so a real regression is never confused with a stale baseline.
    """

    detector: str
    holdout_size: int
    accuracy: float
    baseline_accuracy: float | None = None
    delta: float | None = None  # accuracy - baseline_accuracy
    tolerance: float
    regressed: bool = False
    improved: bool = False
    holdout_sha: str
    baseline_sha: str | None = None
    sha_mismatch: bool = False
    detector_mismatch: bool = False  # baseline.detector != detector
    has_baseline: bool = True
    mismatches: list[DetectorMismatch] = []


# --- Self-heal scenario eval + guard (moat #2: self-heal outcome-match rate) ----
# A labeled scenario replaying one self-heal loop attempt sequence, so the eval
# can score the whole detect->diagnose->patch->outcome loop's outcome-match rate
# against a frozen held-out corpus, mirroring FailureCase/EvalSnapshot/
# HoldoutGuardResult above but for the self-heal loop rather than the detector
# alone.


class AttemptSpec(BaseModel):
    """One attempt's single-task trace row + log; mirrors FailureCase's inputs."""

    status: str
    exit: int
    log_text: str = ""


class HealScenario(BaseModel):
    """One labeled self-heal scenario: attempt trace(s) plus the true outcome.

    Mirrors FailureCase, but carries a full attempt sequence and the expected
    recovery outcome instead of a single expected failure class.
    """

    scenario_id: str
    description: str
    source: str  # provenance: a run id, or "synthetic"
    expected_class: FailureClass
    attempts: list[AttemptSpec]
    auto_approve: bool = False
    poll_decision: Literal["approve", "reject", "timeout"] | None = None
    resource_ceiling: dict[str, int] | None = None
    index_builder_result: Literal["success", "fail"] | None = None
    max_attempts: int = 3
    assay: str = "rnaseq"
    expected_recovered: bool
    expected_outcome: str


class HealClassScore(BaseModel):
    """Per-class outcome-match rate over the scenario corpus; mirrors ClassScore."""

    matched: int
    total: int
    rate: float


class HealScenarioResult(BaseModel):
    """A scenario the self-heal loop diverged on; mirrors DetectorMismatch."""

    scenario_id: str
    diagnosed_class: str | None
    recovered: bool
    actual_outcome: str | None
    matched: bool
    divergence: list[str]


class HealEvalReport(BaseModel):
    """The result of replaying the self-heal loop over a scenario corpus.

    Mirrors DetectorEvalReport, but scores outcome-match rate and recovery
    rate for the whole loop rather than detector accuracy alone.
    """

    total: int
    matched: int
    outcome_match_rate: float
    healed: int
    recovery_rate: float
    per_class: dict[str, HealClassScore] = {}
    mismatches: list[HealScenarioResult] = []


class HealSnapshot(BaseModel):
    """One heal-eval result tied to a corpus version; mirrors EvalSnapshot's
    fields, but not its storage: there is exactly one frozen baseline, not a
    history.

    Serialized as the single committed baseline (one pretty-printed JSON
    object, NOT JSONL) that `evaluate_heal`'s outcome-match rate is compared
    against on every run. There is no history file and no dashboard trend --
    `--history` is explicitly deferred.
    """

    timestamp: str
    scenario_count: int
    corpus_sha: str
    outcome_match_rate: float
    recovery_rate: float
    per_class: dict[str, HealClassScore] = {}
    covered_classes: list[str] = []
    contig_version: str | None = None


class HealGuardResult(BaseModel):
    """The result of scoring the self-heal loop against a frozen held-out
    scenario set and comparing it to a committed baseline; mirrors
    HoldoutGuardResult (C6 slice 2: the self-heal regression guard).
    """

    scenario_count: int
    outcome_match_rate: float
    baseline_match_rate: float | None = None
    delta: float | None = None  # outcome_match_rate - baseline_match_rate
    tolerance: float
    regressed: bool = False
    improved: bool = False
    recovery_rate: float
    corpus_sha: str
    baseline_sha: str | None = None
    sha_mismatch: bool = False
    has_baseline: bool = True
    mismatches: list[HealScenarioResult] = []
