// TypeScript mirror of the Contig engine's serialized models (src/contig/models.py).
// The dashboard reads run_record.json and corpus JSON straight from disk, so these
// shapes must track the Python models. The verdict is serialized by the engine
// (a pydantic computed_field), so the dashboard never re-implements trust logic.

export type Verdict = "pass" | "warn" | "fail" | "unverified";
export type QCStatus = "pass" | "warn" | "fail";
// What kind of check produced a QC result: a content-level metric check (a rule
// pack on MultiQC metrics) or a structural/integrity check on the output files
// themselves (present, non-empty, valid). Mirrors QCKind in the engine. Older
// records predate the field, so an absent value reads as "metric".
export type QCKind = "metric" | "structural";

export interface TaskEvent {
  process: string;
  status: string;
  exit: number | null;
  task_id?: string | null;
  name?: string | null;
}

export interface QCResult {
  check: string;
  status: QCStatus;
  message: string;
  value: number | null;
  expected_range: string | null;
  // "metric" (default) or "structural". A structural check verifies the output
  // files themselves (present, non-empty, valid) rather than a content metric.
  // Older records omit it; the QC panel treats an absent value as "metric".
  kind?: QCKind;
}

export interface ExecutionTarget {
  backend: string;
  container_runtime: string;
  work_dir: string;
  engine?: string;
  credentials_ref?: string | null;
  backend_options?: Record<string, string>;
  resource_limits?: Record<string, string>;
}

export interface Diagnosis {
  failure_class: string;
  root_cause: string;
  evidence: string[];
  confidence: number;
}

export interface Patch {
  kind: string;
  operation: Record<string, unknown>;
  rationale: string;
  risk: string;
  expected_signal: string;
}

export interface RepairStep {
  attempt: number;
  diagnosis: Diagnosis;
  patch: Patch | null;
  outcome: string;
}

// Per-task resource actuals parsed from Nextflow's trace.txt and recorded by the
// engine at finalize (PRD contract B). realtime_sec is the task wall-clock in
// seconds; peak_rss_mb is its peak resident memory in MB; pct_cpu is the trace
// %cpu column. name is the concrete task instance (may be null for a process row).
export interface TaskResource {
  process: string;
  name: string | null;
  realtime_sec: number;
  peak_rss_mb: number;
  pct_cpu: number;
}

export interface RunRecord {
  run_id: string;
  pipeline: string;
  pipeline_revision: string;
  target: ExecutionTarget;
  input_checksums: Record<string, string>;
  parameters: Record<string, unknown>;
  container_digests: Record<string, string>;
  nextflow_version: string | null;
  contig_version: string | null;
  events: TaskEvent[];
  qc_results: QCResult[];
  output_checksums: Record<string, string>;
  repair_history: RepairStep[];
  // Per-task duration, peak memory, and cpu, parsed from the run's trace. Empty
  // for older runs (predating resource capture) and for runs with no trace.
  resource_usage: TaskResource[];
  verdict: Verdict;
}

// The cost report from `contig cost <id> --json` (PRD contract B). The engine
// applies the configured rates to the recorded resource usage and reports the
// total and per-task cost. Rates default to 0 (local compute is free), so the
// default total is 0; entering rates yields a real estimate. by_task is empty
// when the run recorded no resource usage.
export interface CostByTask {
  name: string;
  realtime_sec: number;
  peak_rss_mb: number;
  cost: number;
}

export interface CostReport {
  currency: string;
  rate_cpu_hour: number;
  rate_mem_gb_hour: number;
  total: number;
  by_task: CostByTask[];
}

// Detector eval (src/contig/models.py: DetectorEvalReport).
export interface ClassScore {
  support: number;
  predicted: number;
  correct: number;
  precision: number;
  recall: number;
}

export interface DetectorMismatch {
  case_id: string;
  expected: string;
  predicted: string;
}

export interface DetectorEvalReport {
  total: number;
  correct: number;
  accuracy: number;
  mismatches: DetectorMismatch[];
  per_class: Record<string, ClassScore>;
}

// A proposed analysis plan (mirror of Plan in src/contig/models.py), produced by
// `contig plan --json` and shown for approval before a run is launched.
export interface Plan {
  assay: string;
  pipeline: string;
  revision: string;
  params: Record<string, unknown>;
  rationale: string;
  warnings: string[];
}

// Run lifecycle marker (runs/<id>/status.json), written by the engine so a run
// is observable while in flight (run_record.json only appears at the end).
export interface RunStatus {
  run_id: string;
  state: "running" | "finished" | "error" | "cancelled" | "awaiting_approval";
  started_at: string;
  finished_at: string | null;
  pid?: number;
}

// One ranked option in a guided-escalation choice (PRD contract D). When the
// self-heal decision is ambiguous (a low-confidence diagnosis, or several viable
// non-safe candidate patches and no single safe one), the engine writes an options
// array ordered best first, and the human picks one. index is the position the CLI
// applies via `contig approve <id> --choose <index>`; kind, risk, rationale, and
// expected_signal mirror the patch fields the single gate shows.
export interface ApprovalOption {
  index: number;
  kind: string;
  risk: string;
  rationale: string;
  expected_signal: string;
}

// A pending self-heal approval (runs/<id>/pending_approval.json, PRD contracts C
// and D). Written by the engine when the loop pauses on a gated decision; the
// dashboard reads it to render the gate. Absent when no decision is awaiting.
//
// Two shapes share this file, distinguished by decision_kind:
//   - "single" (or absent, for back-compat): one proposed patch, rendered with
//     Approve and Reject. This is the existing binary gate.
//   - "choice": the decision is ambiguous, so options carries the ranked fixes and
//     the human picks one. The single patch fields stay populated for back-compat
//     (they mirror options[0]); the dashboard renders the choice list when options
//     is present.
export interface PendingApproval {
  run_id: string;
  attempt: number;
  requested_at: string;
  timeout_sec: number;
  diagnosis: Diagnosis;
  patch: Patch;
  // "single" (the binary gate) or "choice" (the ranked options below). Absent on
  // older records, which the dashboard treats as "single".
  decision_kind?: "single" | "choice";
  // The ranked fixes for a "choice" decision, best first. Absent for a single gate.
  options?: ApprovalOption[];
}

// The cross-run benchmark report from `contig benchmark <id> --json` (PRD contract
// A). The engine compares a run against the designated reference for its (pipeline,
// assay) by QC metric values within a relative tolerance plus structural shape (the
// same QC check names present), robust to run-to-run non-determinism. status is
// "match" when nothing drifted, "drift" when at least one shared metric is out of
// tolerance or the shape differs, and "no_reference" when no reference is recorded
// for this pipeline/assay (a clear state, not an error). Each check carries the run
// value, the reference value, whether it is within tolerance, and the delta.
export interface BenchmarkCheck {
  name: string;
  run_value: number | null;
  reference_value: number | null;
  within_tolerance: boolean;
  delta: number | null;
}

export interface BenchmarkReport {
  reference_run_id: string | null;
  tolerance: number;
  matched: number;
  drifted: number;
  checks: BenchmarkCheck[];
  status: "match" | "drift" | "no_reference";
}

// One failure cluster from `contig clusters --json` (PRD contract B). The engine
// groups corpus and pending cases by failure_class plus a normalized log signature
// (lowercase, absolute paths, numbers, hashes, and timestamps stripped, salient
// lines hashed), so the same systemic failure mode groups even across runs. count
// is how many cases fall in the cluster; case_ids lists them. The clusters view
// renders these worst first (largest count).
export interface FailureCluster {
  failure_class: string;
  signature: string;
  count: number;
  case_ids: string[];
}

// The corpus coverage report from `contig coverage --json` (PRD contract C). total
// is the case count; per_class maps each failure class to its support; thin lists
// the classes with fewer than 3 cases (a coverage gap); by_source maps each source
// kind to its count. confirmed_over_time, when present, is a confirmed-cases series
// derived from the eval history (timestamp + corpus_size), so the panel can show
// growth. The dashboard renders per-class support bars and flags the thin classes.
export interface CoveragePoint {
  timestamp: string;
  confirmed: number;
}

export interface CoverageReport {
  total: number;
  per_class: Record<string, number>;
  thin: string[];
  by_source: Record<string, number>;
  confirmed_over_time?: CoveragePoint[];
}

// One eval snapshot (src/contig/data/eval_history.jsonl, PRD contract D). The
// engine appends one per line on `eval-detector --snapshot` and on corpus-promote;
// the /eval trend reads them to plot accuracy over time and per-class deltas.
export interface EvalSnapshot {
  timestamp: string;
  corpus_size: number;
  corpus_sha: string;
  accuracy: number;
  per_class: Record<string, ClassScore>;
  contig_version: string | null;
  // Which detector produced this snapshot (PRD contract A): "rules" (default),
  // "rules-strict", or "llm". Older snapshots predate the field; the dashboard
  // treats an absent value as "rules" so the compare view always has a bucket.
  detector?: string;
}

// The pre-run estimate from `contig estimate --json` (PRD contract B). The engine
// scans prior FINISHED runs of the same pipeline to derive a per-sample resource
// total and scales it to the requested sample count; with no history it falls
// back to a transparent heuristic. basis says which path produced the figures.
// Rates default to 0 (local compute is free), so est_cost is 0 unless rates are
// passed. note carries a short human-readable caveat. The dashboard reads this on
// the launch form to show runtime and cost before a run starts.
export interface EstimateReport {
  basis: "history" | "heuristic";
  pipeline: string;
  n_samples: number;
  n_prior_runs: number;
  est_runtime_sec: number;
  est_peak_mem_mb: number;
  est_total_cpu_hours: number;
  est_cost: number;
  currency: string;
  rate_cpu_hour: number;
  rate_mem_gb_hour: number;
  note: string;
}

export interface FailureCase {
  case_id: string;
  description: string;
  source: string;
  events: TaskEvent[];
  log_text: string;
  expected_class: string;
}

// A self-heal attempt as the live view consumes it: one parsed line of
// repair_progress.jsonl (a RepairStep the engine appends as each attempt
// resolves). The shape is the RepairStep above, narrowed to what the live
// summary renders.
export interface RepairStepLite {
  attempt: number;
  diagnosis: Diagnosis;
  patch: Patch | null;
  outcome: string;
}

// A live snapshot of an in-flight (or just finished) run, derived server-side
// from status.json, trace.txt, and repair_progress.jsonl (PRD contract C).
export interface RunProgress {
  state:
    | "running"
    | "awaiting_approval"
    | "cancelled"
    | "finished"
    | "interrupted"
    | "missing";
  startedAt: string | null;
  // Seconds from startedAt to finishedAt (if finished) or now (if running).
  elapsedSec: number | null;
  // trace rows whose status is COMPLETED.
  tasksCompleted: number;
  // trace rows whose status is RUNNING, with the process and (optional) name.
  tasksRunning: { process: string; name: string | null }[];
  // Total trace rows seen so far (optional honesty signal, not a denominator).
  submitted: number | null;
  // Self-heal attempts parsed from repair_progress.jsonl, in order.
  repairs: RepairStepLite[];
}

// One lifecycle event the engine appends to <runsDir>/notifications.jsonl (PRD
// contract A). The header bell reads these (newest first) into an activity panel;
// an awaiting_approval event links to its run. The kind set is closed so the panel
// only ever renders events it knows how to style.
export type NotificationKind =
  | "finished"
  | "failed"
  | "cancelled"
  | "awaiting_approval";

export interface NotificationEvent {
  ts: string;
  run_id: string;
  kind: NotificationKind;
  message: string;
}

// The output-integrity report from `contig verify <id> --json` (PRD contract B).
// The engine re-hashes a run's recorded output files on disk against the
// checksums in run_record.json; ok is true when none drifted. changed lists files
// whose hash no longer matches, missing lists recorded files now absent. An empty
// recorded checksum set means there was nothing to verify (the run detail page
// renders that as a neutral "not captured" badge rather than a pass or a fail).
export interface OutputVerification {
  ok: boolean;
  changed: string[];
  missing: string[];
  // Signed-record fields (PRD contract E), present only when a run carries a
  // signature.json sidecar. `signed` is true when a signature was found; when it
  // is, `signature_ok` is the result of checking the detached Ed25519 signature
  // against the recomputed content hash (true verified, false tampered). Absent
  // for a run with no signature, so the badge stays neutral.
  signed?: boolean;
  signature_ok?: boolean;
}

// The launch manifest a run writes before self_heal_run (PRD contract A). The
// reproduce path reads this to rebuild an identical run with a fresh id.
export interface LaunchManifest {
  run_id: string;
  pipeline: string;
  revision: string;
  profiles: string[];
  backend: string;
  container_runtime: string;
  input: string | null;
  genome: string | null;
  fasta: string | null;
  gtf: string | null;
  max_memory: string | null;
  max_cpus: number | null;
  max_attempts: number;
  is_test_profile: boolean;
  created_at: string;
}

// The owner tag a dispatch route writes to runs/<id>/owner.json (PRD contract E).
// owner is the stable user identity (the Auth0 `sub`); email is the address if
// the tenant exposes one. A run with no owner.json predates ownership (e.g. a
// CLI-launched run) and is admin-only. Under the auth bypass the owner is the
// synthetic local admin, so local dev and the e2e suite see every run.
export interface RunOwner {
  owner: string;
  email: string | null;
}
