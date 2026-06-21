// TypeScript mirror of the Contig engine's serialized models (src/contig/models.py).
// The dashboard reads run_record.json and corpus JSON straight from disk, so these
// shapes must track the Python models. The verdict is serialized by the engine
// (a pydantic computed_field), so the dashboard never re-implements trust logic.

export type Verdict = "pass" | "warn" | "fail" | "unverified";
export type QCStatus = "pass" | "warn" | "fail";

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
  verdict: Verdict;
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
  state: "running" | "finished" | "error";
  started_at: string;
  finished_at: string | null;
  pid?: number;
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
  state: "running" | "finished" | "interrupted" | "missing";
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
