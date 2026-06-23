// Server-side disk access to the Contig engine's artifacts. This module is the
// single data layer the pages call. It reads run_record.json bundles and the
// corpus JSON directly from the runs directory, and shells out to the Python CLI
// only for the detector eval (the detector is the moat and stays in Python).
//
// "server-only" guards against importing this into a client component by mistake.
import "server-only";

import { promises as fs } from "fs";
import path from "path";
import { execFile, spawn } from "child_process";
import { promisify } from "util";

import type {
  BenchmarkReport,
  CostReport,
  CoverageReport,
  DetectorEvalReport,
  EstimateReport,
  EvalSnapshot,
  FailureCase,
  FailureCluster,
  LaunchManifest,
  NotificationEvent,
  OutputVerification,
  PendingApproval,
  Plan,
  RepairStepLite,
  RunOwner,
  RunProgress,
  RunRecord,
  RunStatus,
} from "./types";
import { canViewRun, filterOwnedRunIds, type Viewer } from "./ownership";

// Re-export the pure isolation rule so callers can keep importing it from the data
// layer; the rule itself lives in lib/ownership.ts (no server-only guard) so it is
// unit-testable in isolation (PRD contract E).
export { canViewRun, filterOwnedRunIds, type Viewer };

const pexec = promisify(execFile);

/** Absolute path to the runs directory (CONTIG_RUNS_DIR, default ../runs). */
export function runsDir(): string {
  return process.env.CONTIG_RUNS_DIR
    ? path.resolve(process.env.CONTIG_RUNS_DIR)
    : path.resolve(process.cwd(), "..", "runs");
}

/** Repo root, where `contig` runs (one level up from dashboard/). */
function repoRoot(): string {
  return path.resolve(process.cwd(), "..");
}

async function readRecord(id: string): Promise<RunRecord | null> {
  const p = path.join(runsDir(), id, "run_record.json");
  try {
    return JSON.parse(await fs.readFile(p, "utf8")) as RunRecord;
  } catch {
    return null;
  }
}

/**
 * Run bundles found on disk, filtered to the ones the viewer may see (PRD contract
 * E). A user sees only runs they own; an admin (and the bypass) sees all; a run
 * with no owner.json is admin-only. Directories without a run_record.json are
 * skipped. Without a viewer (legacy callers) every bundle is returned, so the raw
 * disk listing is still available where isolation does not apply.
 */
export async function listRuns(viewer?: Viewer): Promise<RunRecord[]> {
  let entries: string[];
  try {
    entries = await fs.readdir(runsDir());
  } catch {
    return [];
  }
  const records = await Promise.all(entries.map((name) => readRecord(name)));
  const present = records.filter((r): r is RunRecord => r !== null);
  if (!viewer) return present;
  // An admin (and the bypass) sees everything, so skip the per-run owner reads.
  if (viewer.isAdmin) return present;
  const owned = await Promise.all(
    present.map(async (r) => ({
      record: r,
      visible: canViewRun(viewer, await getRunOwner(r.run_id)),
    })),
  );
  return owned.filter((o) => o.visible).map((o) => o.record);
}

/**
 * One run bundle by id, or null if absent OR the viewer may not see it (PRD
 * contract E): a run the user does not own (and is not admin for) reads as absent,
 * so the detail page 404s rather than leaking another user's run. Without a viewer
 * the raw bundle is returned (legacy callers that do not apply isolation).
 */
export async function getRun(
  id: string,
  viewer?: Viewer,
): Promise<RunRecord | null> {
  const record = await readRecord(id);
  if (!record) return null;
  if (!viewer) return record;
  if (!canViewRun(viewer, await getRunOwner(id))) return null;
  return record;
}

/** The lifecycle marker for a run (running/finished/error), or null if none. */
export async function getRunStatus(id: string): Promise<RunStatus | null> {
  const p = path.join(runsDir(), id, "status.json");
  try {
    return JSON.parse(await fs.readFile(p, "utf8")) as RunStatus;
  } catch {
    return null;
  }
}

/** Whether a process id is still alive (used to detect interrupted runs). */
function isProcessAlive(pid?: number): boolean {
  if (!pid) return false;
  try {
    process.kill(pid, 0);
    return true;
  } catch (err) {
    // EPERM means the process exists but we cannot signal it (still alive).
    return (err as NodeJS.ErrnoException).code === "EPERM";
  }
}

/** A run is genuinely in flight only if its marker says running AND its pid is alive. */
function isLive(status: RunStatus | null): boolean {
  return status?.state === "running" && isProcessAlive(status.pid);
}

/**
 * A run is active (occupies the single run slot) when it is running OR paused
 * awaiting approval AND its pid is alive. A paused run still holds the slot, so a
 * new dispatch must wait for it to finish, cancel, or be resolved.
 */
function isActive(status: RunStatus | null): boolean {
  return (
    (status?.state === "running" || status?.state === "awaiting_approval") &&
    isProcessAlive(status.pid)
  );
}

export type RunState =
  | "finished"
  | "running"
  | "awaiting_approval"
  | "cancelled"
  | "interrupted"
  | "missing";

/**
 * Resolve a run's state. A "running" or "awaiting_approval" marker whose process
 * has died (no bundle) is "interrupted", not a stuck active run: a crashed or
 * cancelled run must not block new dispatches or poll forever. "cancelled" is a
 * terminal state the engine writes, so it is honored regardless of pid liveness.
 */
export async function getRunState(id: string): Promise<RunState> {
  if (await readRecord(id)) return "finished";
  const status = await getRunStatus(id);
  if (!status) return "missing";
  if (status.state === "cancelled") return "cancelled";
  // A paused run waits with a live pid (it polls for approval.json). If that pid
  // is dead the run was interrupted while paused, so fall through like running.
  if (status.state === "awaiting_approval") {
    return isProcessAlive(status.pid) ? "awaiting_approval" : "interrupted";
  }
  return isLive(status) ? "running" : "interrupted";
}

/** Runs that are genuinely in flight: a live "running" process and no bundle yet. */
export async function listRunningRuns(): Promise<
  { run_id: string; started_at: string }[]
> {
  let entries: string[];
  try {
    entries = await fs.readdir(runsDir());
  } catch {
    return [];
  }
  const out: { run_id: string; started_at: string }[] = [];
  for (const name of entries) {
    if (await readRecord(name)) continue; // already finished
    const st = await getRunStatus(name);
    // A paused (awaiting_approval) run still occupies the single run slot, so it
    // counts as active and blocks a fresh dispatch until it resolves.
    if (isActive(st)) out.push({ run_id: name, started_at: st!.started_at });
  }
  return out;
}

// --- Live progress (PRD contract C) -------------------------------------------
// Derived server-side from status.json, trace.txt, and repair_progress.jsonl.
// The view stays honest: it reports completed and running counts but never
// invents a percentage, because the total task count is not known up front.

/** Strip ANSI escape sequences so the log tail renders as plain text. */
const ANSI = /\[[0-9;]*[A-Za-z]/g;

/**
 * Parse Nextflow's trace.txt (a TSV with a header row). The columns vary by
 * config, so we find `status`, `name`, and `process` BY HEADER NAME and never
 * hard-code indices. Returns the completed count and the running rows.
 */
function parseTrace(text: string): {
  tasksCompleted: number;
  tasksRunning: { process: string; name: string | null }[];
  submitted: number;
} {
  const lines = text.split("\n").filter((l) => l.trim().length > 0);
  if (lines.length === 0) {
    return { tasksCompleted: 0, tasksRunning: [], submitted: 0 };
  }
  const header = lines[0].split("\t").map((h) => h.trim().toLowerCase());
  const statusIdx = header.indexOf("status");
  const nameIdx = header.indexOf("name");
  const processIdx = header.indexOf("process");
  let tasksCompleted = 0;
  const tasksRunning: { process: string; name: string | null }[] = [];
  const rows = lines.slice(1);
  for (const row of rows) {
    const cols = row.split("\t");
    const status = (statusIdx >= 0 ? cols[statusIdx] : "").trim().toUpperCase();
    if (status === "COMPLETED") {
      tasksCompleted += 1;
    } else if (status === "RUNNING") {
      const name = nameIdx >= 0 ? (cols[nameIdx] ?? "").trim() : "";
      const process = processIdx >= 0 ? (cols[processIdx] ?? "").trim() : "";
      tasksRunning.push({
        process: process || name || "task",
        name: name.length > 0 ? name : null,
      });
    }
  }
  return { tasksCompleted, tasksRunning, submitted: rows.length };
}

/** Parse repair_progress.jsonl: one RepairStep per line, skip malformed lines. */
function parseRepairProgress(text: string): RepairStepLite[] {
  const out: RepairStepLite[] = [];
  for (const line of text.split("\n")) {
    if (line.trim().length === 0) continue;
    try {
      out.push(JSON.parse(line) as RepairStepLite);
    } catch {
      // A half-written final line (the engine appends concurrently) is ignored.
    }
  }
  return out;
}

/**
 * A live snapshot of a run, derived from status.json, trace.txt, and
 * repair_progress.jsonl. Mirrors PRD contract C. Missing files degrade to empty
 * (no trace yet means zero tasks, not an error).
 */
export async function getRunProgress(id: string): Promise<RunProgress> {
  const dir = path.join(runsDir(), id);
  const state = await getRunState(id);
  const status = await getRunStatus(id);
  const startedAt = status?.started_at ?? null;

  let elapsedSec: number | null = null;
  if (startedAt) {
    const start = Date.parse(startedAt);
    if (!Number.isNaN(start)) {
      const end =
        status?.finished_at && !Number.isNaN(Date.parse(status.finished_at))
          ? Date.parse(status.finished_at)
          : Date.now();
      elapsedSec = Math.max(0, Math.round((end - start) / 1000));
    }
  }

  let trace = { tasksCompleted: 0, tasksRunning: [] as { process: string; name: string | null }[], submitted: 0 };
  try {
    trace = parseTrace(await fs.readFile(path.join(dir, "trace.txt"), "utf8"));
  } catch {
    // No trace yet (early in the run, or this run never wrote one).
  }

  let repairs: RepairStepLite[] = [];
  try {
    repairs = parseRepairProgress(
      await fs.readFile(path.join(dir, "repair_progress.jsonl"), "utf8"),
    );
  } catch {
    // No repairs yet (no failure has resolved).
  }

  return {
    state,
    startedAt,
    elapsedSec,
    tasksCompleted: trace.tasksCompleted,
    tasksRunning: trace.tasksRunning,
    submitted: trace.submitted > 0 ? trace.submitted : null,
    repairs,
  };
}

/**
 * The last N lines of run.log with ANSI stripped, for the collapsible log tail.
 * Returns an empty string if there is no log yet (the run just started).
 */
export async function getRunLogTail(id: string, lines = 200): Promise<string> {
  const p = path.join(runsDir(), id, "run.log");
  let text: string;
  try {
    text = await fs.readFile(p, "utf8");
  } catch {
    return "";
  }
  const all = text.replace(ANSI, "").split("\n");
  // Drop a trailing empty line so the tail does not render a blank final row.
  if (all.length > 0 && all[all.length - 1] === "") all.pop();
  return all.slice(Math.max(0, all.length - lines)).join("\n");
}

/**
 * Promote a reviewed pending case into the golden corpus by shelling out to the
 * CLI (the corpus write logic stays in Python, the moat). label, when given,
 * corrects the provisional class. Throws if the CLI fails (e.g. unknown case).
 */
export async function promotePendingCase(caseId: string, label?: string): Promise<void> {
  const override = process.env.CONTIG_CMD;
  const cmd = override ?? "uv";
  // Options first, then "--" so caseId is always parsed as a positional argument
  // and can never be smuggled in as a CLI flag, even if a caller skips validation.
  const args = (override ? [] : ["run", "contig"]).concat([
    "corpus-promote",
    "--pending",
    path.join(runsDir(), "pending_corpus.jsonl"),
    ...(label ? ["--label", label] : []),
    "--",
    caseId,
  ]);
  await pexec(cmd, args, { cwd: repoRoot(), timeout: 30_000 });
}

/** Raised when a run is already in flight (v1 allows one at a time). */
export class DispatchBusyError extends Error {
  constructor(public readonly runningId: string) {
    super(`A run is already in progress: ${runningId}`);
    this.name = "DispatchBusyError";
  }
}

/** Raised when a launch request is invalid (bad path, key, or caps). */
export class LaunchValidationError extends Error {}

/** A short key (iGenomes name, pipeline) with no leading dash and a safe charset. */
function isSafeKey(value: string): boolean {
  return /^[A-Za-z0-9._/-]+$/.test(value) && !value.startsWith("-");
}

async function assertFile(value: string, label: string): Promise<string> {
  if (typeof value !== "string" || value.length === 0 || value.startsWith("-")) {
    throw new LaunchValidationError(`${label} is required and must be a real path.`);
  }
  const abs = path.resolve(value);
  try {
    if (!(await fs.stat(abs)).isFile()) throw new Error();
  } catch {
    throw new LaunchValidationError(`${label} not found: ${value}`);
  }
  return abs;
}

// Reference is exactly one of: an iGenomes key, or a fasta + gtf pair.
async function resolveReferenceArgs(req: {
  genome?: string;
  fasta?: string;
  gtf?: string;
}): Promise<string[]> {
  const hasGenome = !!req.genome;
  const hasExplicit = !!req.fasta || !!req.gtf;
  if (hasGenome && hasExplicit) {
    throw new LaunchValidationError("Provide either a genome key or fasta + gtf, not both.");
  }
  if (hasGenome) {
    if (!isSafeKey(req.genome as string)) {
      throw new LaunchValidationError("Invalid genome key.");
    }
    return [`--genome=${req.genome}`];
  }
  if (req.fasta && req.gtf) {
    const fasta = await assertFile(req.fasta, "FASTA");
    const gtf = await assertFile(req.gtf, "GTF");
    return [`--fasta=${fasta}`, `--gtf=${gtf}`];
  }
  throw new LaunchValidationError("A reference is required: a genome key, or both fasta and gtf.");
}

const KNOWN_PIPELINES = new Set(["nf-core/rnaseq", "nf-core/sarek"]);

// The execution backends and engines the launch form may select (PRD contract F).
// "local" + "nextflow" are the defaults, so the common path is unchanged. Slurm
// adds a partition (passed as --queue) and an account; snakemake is the alternate
// engine. The set is closed so an unknown value never reaches the CLI.
const KNOWN_BACKENDS = new Set(["local", "slurm"]);
const KNOWN_ENGINES = new Set(["nextflow", "snakemake"]);

/**
 * Append validated backend and engine knobs to a dispatch argv (PRD contract F).
 * Local + nextflow are the defaults and add nothing, so an unchanged form dispatches
 * exactly as before. A slurm backend threads --backend=slurm plus the partition as
 * --queue=<partition> and an optional --account; a snakemake engine threads
 * --engine=snakemake. Every value is validated (safe key charset, no leading dash)
 * and passed as --opt=value, so there is no flag-smuggling surface. Throws
 * LaunchValidationError on an unknown backend/engine or a malformed partition/account.
 */
function backendEngineArgs(req: {
  backend?: string;
  engine?: string;
  queue?: string;
  account?: string;
}): string[] {
  const out: string[] = [];
  if (req.backend && req.backend !== "local") {
    if (!KNOWN_BACKENDS.has(req.backend)) {
      throw new LaunchValidationError("Unknown backend.");
    }
    out.push(`--backend=${req.backend}`);
    if (req.backend === "slurm") {
      // A slurm run needs a partition (the queue). The account is optional but
      // required by many clusters; we pass it through when present.
      if (!req.queue || !isSafeKey(req.queue)) {
        throw new LaunchValidationError("A slurm partition is required.");
      }
      out.push(`--queue=${req.queue}`);
      if (req.account) {
        if (!isSafeKey(req.account)) {
          throw new LaunchValidationError("Invalid slurm account.");
        }
        out.push(`--account=${req.account}`);
      }
    }
  }
  if (req.engine && req.engine !== "nextflow") {
    if (!KNOWN_ENGINES.has(req.engine)) {
      throw new LaunchValidationError("Unknown engine.");
    }
    out.push(`--engine=${req.engine}`);
  }
  return out;
}

/**
 * Produce an approvable plan for a goal + data by shelling out to `contig plan
 * --json`. Returns the plan, or an error string the form can show. All user
 * values pass as `--opt=value` (bound to their option, no flag smuggling).
 */
export async function planRun(req: {
  goal: string;
  input: string;
  genome?: string;
  fasta?: string;
  gtf?: string;
}): Promise<{ plan?: Plan; error?: string }> {
  let refArgs: string[];
  let input: string;
  try {
    if (typeof req.goal !== "string" || req.goal.trim().length === 0) {
      return { error: "A goal is required." };
    }
    input = await assertFile(req.input, "Sample sheet");
    refArgs = await resolveReferenceArgs(req);
  } catch (err) {
    return { error: err instanceof LaunchValidationError ? err.message : "Invalid request." };
  }

  const override = process.env.CONTIG_CMD;
  const cmd = override ?? "uv";
  const args = (override ? [] : ["run", "contig"]).concat([
    "plan",
    "--json",
    `--goal=${req.goal}`,
    `--input=${input}`,
    ...refArgs,
  ]);
  try {
    const { stdout } = await pexec(cmd, args, { cwd: repoRoot(), timeout: 30_000 });
    const data = JSON.parse(stdout) as Plan & { error?: string };
    if (data.error) return { error: data.error };
    return { plan: data };
  } catch (err) {
    const out = (err as { stdout?: string })?.stdout;
    if (typeof out === "string") {
      try {
        const d = JSON.parse(out) as { error?: string };
        if (d.error) return { error: d.error };
      } catch {
        /* fall through */
      }
    }
    return { error: "Could not produce a plan." };
  }
}

/**
 * Launch a real-data run: validate inputs, then spawn `contig run` detached with
 * the resolved arguments. One at a time. The run id is generated server-side and
 * every user value is passed as `--opt=value`, so there is no flag-smuggling
 * surface. Throws LaunchValidationError on bad input, DispatchBusyError if busy.
 */
export async function dispatchRealRun(req: {
  input: string;
  pipeline?: string;
  genome?: string;
  fasta?: string;
  gtf?: string;
  maxMemory?: string;
  maxCpus?: string;
  backend?: string;
  engine?: string;
  queue?: string;
  account?: string;
}): Promise<{ run_id: string }> {
  const running = await listRunningRuns();
  if (running.length > 0) throw new DispatchBusyError(running[0].run_id);

  const input = await assertFile(req.input, "Sample sheet");
  const refArgs = await resolveReferenceArgs(req);
  const extra: string[] = [];
  if (req.pipeline) {
    if (!KNOWN_PIPELINES.has(req.pipeline)) {
      throw new LaunchValidationError("Unknown pipeline.");
    }
    extra.push(`--pipeline=${req.pipeline}`);
  }
  if (req.maxMemory) {
    if (!/^[0-9][0-9.]*\.?[A-Za-z]{1,3}$/.test(req.maxMemory)) {
      throw new LaunchValidationError("Invalid memory cap (e.g. 6.GB).");
    }
    extra.push(`--max-memory=${req.maxMemory}`);
  }
  if (req.maxCpus) {
    if (!/^[0-9]+$/.test(req.maxCpus)) {
      throw new LaunchValidationError("Invalid cpu cap.");
    }
    extra.push(`--max-cpus=${req.maxCpus}`);
  }
  // Backend and engine selectors (PRD contract F). Local + nextflow add nothing.
  extra.push(
    ...backendEngineArgs({
      backend: req.backend,
      engine: req.engine,
      queue: req.queue,
      account: req.account,
    }),
  );

  const stamp = new Date().toISOString().replace(/[:.]/g, "-");
  const runId = `run-${stamp}`;
  const base = (process.env.CONTIG_DISPATCH_CMD ?? "uv run contig").split(" ");
  const args = [
    ...base.slice(1),
    "run",
    `--run-id=${runId}`,
    `--runs-dir=${runsDir()}`,
    `--input=${input}`,
    ...refArgs,
    ...extra,
  ];
  const child = spawn(base[0], args, {
    cwd: repoRoot(),
    detached: true,
    stdio: "ignore",
  });
  child.unref();
  return { run_id: runId };
}

/**
 * Launch a test-profile run (no inputs) by spawning the existing CLI detached.
 * One at a time: refuses if a run is already in flight. argv array, never a
 * shell string, so there is no injection surface. The engine writes status.json
 * and, at the end, run_record.json; the dashboard observes the run dir.
 */
export async function dispatchTestProfileRun(): Promise<{ run_id: string }> {
  const running = await listRunningRuns();
  if (running.length > 0) throw new DispatchBusyError(running[0].run_id);

  const stamp = new Date().toISOString().replace(/[:.]/g, "-");
  const runId = `test-${stamp}`;
  // Default: `uv run contig`. Override with CONTIG_DISPATCH_CMD (space separated).
  const base = (process.env.CONTIG_DISPATCH_CMD ?? "uv run contig").split(" ");
  const args = [
    ...base.slice(1),
    "run",
    "--run-id",
    runId,
    "--runs-dir",
    runsDir(),
  ];
  const child = spawn(base[0], args, {
    cwd: repoRoot(),
    detached: true,
    stdio: "ignore",
  });
  child.unref();
  return { run_id: runId };
}

// --- Reproduce (PRD contract A + F) -------------------------------------------
// A run writes launch.json before self_heal_run, so every run is reproducible.
// Reproduce reads that manifest, re-validates the inputs (we never trust the
// manifest blindly), and dispatches an identical run with a FRESH run id.

/** The launch manifest a run wrote (runs/<id>/launch.json), or null if absent. */
export async function getLaunchManifest(id: string): Promise<LaunchManifest | null> {
  const p = path.join(runsDir(), id, "launch.json");
  try {
    return JSON.parse(await fs.readFile(p, "utf8")) as LaunchManifest;
  } catch {
    return null;
  }
}

/** Raised when a run cannot be reproduced (no manifest to rebuild it from). */
export class NoManifestError extends Error {}

/**
 * Reproduce a run exactly: read its launch.json, re-validate the inputs as
 * dispatchRealRun does (paths exist, safe keys, valid caps), then dispatch an
 * identical run with a fresh server-generated run id. Test-profile runs (no
 * input) re-dispatch via the test path. Every user-derived value passes as
 * --opt=value and positionals are guarded by a -- terminator, so there is no
 * flag-smuggling surface even though the values originate from a sidecar file.
 */
export async function dispatchReproduce(id: string): Promise<{ run_id: string }> {
  const manifest = await getLaunchManifest(id);
  if (!manifest) throw new NoManifestError(`No launch manifest for run ${id}.`);

  const running = await listRunningRuns();
  if (running.length > 0) throw new DispatchBusyError(running[0].run_id);

  const stamp = new Date().toISOString().replace(/[:.]/g, "-");
  const runId = `run-${stamp}`;
  const base = (process.env.CONTIG_DISPATCH_CMD ?? "uv run contig").split(" ");

  // A test-profile run has no input: re-dispatch it as a test run so the same
  // path runs again. Nothing user-derived needs validation here.
  if (manifest.is_test_profile || manifest.input === null) {
    const args = [
      ...base.slice(1),
      "run",
      `--run-id=${runId}`,
      `--runs-dir=${runsDir()}`,
    ];
    const child = spawn(base[0], args, {
      cwd: repoRoot(),
      detached: true,
      stdio: "ignore",
    });
    child.unref();
    return { run_id: runId };
  }

  // Real run: re-validate every input from the manifest before we trust it.
  const input = await assertFile(manifest.input, "Sample sheet");
  const refArgs = await resolveReferenceArgs({
    genome: manifest.genome ?? undefined,
    fasta: manifest.fasta ?? undefined,
    gtf: manifest.gtf ?? undefined,
  });
  const extra: string[] = [];
  if (manifest.pipeline) {
    if (!KNOWN_PIPELINES.has(manifest.pipeline)) {
      throw new LaunchValidationError("Unknown pipeline.");
    }
    extra.push(`--pipeline=${manifest.pipeline}`);
  }
  if (manifest.max_memory) {
    if (!/^[0-9][0-9.]*\.?[A-Za-z]{1,3}$/.test(manifest.max_memory)) {
      throw new LaunchValidationError("Invalid memory cap (e.g. 6.GB).");
    }
    extra.push(`--max-memory=${manifest.max_memory}`);
  }
  if (manifest.max_cpus !== null && manifest.max_cpus !== undefined) {
    if (!Number.isInteger(manifest.max_cpus) || manifest.max_cpus <= 0) {
      throw new LaunchValidationError("Invalid cpu cap.");
    }
    extra.push(`--max-cpus=${manifest.max_cpus}`);
  }

  const args = [
    ...base.slice(1),
    "run",
    `--run-id=${runId}`,
    `--runs-dir=${runsDir()}`,
    `--input=${input}`,
    ...refArgs,
    ...extra,
  ];
  const child = spawn(base[0], args, {
    cwd: repoRoot(),
    detached: true,
    stdio: "ignore",
  });
  child.unref();
  return { run_id: runId };
}

// The detectors the engine registers (the pinned `DETECTORS` registry keys, PRD
// contract C). "rules" is the default; "rules-strict" prefers unknown/tool_crash
// when evidence is weak; "llm" is the optional provider-agnostic LLM detector,
// resolvable only when a provider + key are configured (without one, the engine
// returns the graceful not-available branch, which the page already renders).
// The /eval selector offers exactly these names, and a query value not in this
// set falls back to the default so the CLI is never handed an unknown detector.
export const DETECTOR_NAMES = ["rules", "rules-strict", "llm"] as const;
export type DetectorName = (typeof DETECTOR_NAMES)[number];

/** Whether a value is one of the registered detector names. */
export function isDetectorName(value: string | undefined): value is DetectorName {
  return (DETECTOR_NAMES as readonly string[]).includes(value ?? "");
}

/**
 * The detector eval for a named detector, obtained by shelling out to `contig
 * eval-detector --detector <name> --json` (the detector is Python, the moat; we
 * never re-implement it in TS). The detector name is constrained to the known
 * registry keys before it reaches the CLI, and it is passed as `--detector=<name>`
 * so it can never be parsed as a separate flag. Returns null if the CLI is
 * unavailable, so the page can degrade gracefully. Defaults to "rules".
 */
export async function getDetectorEval(
  detector: DetectorName = "rules",
): Promise<DetectorEvalReport | null> {
  // Guard again at the boundary: only a known detector name is ever shelled out,
  // even if a caller bypasses isDetectorName upstream.
  const name: DetectorName = isDetectorName(detector) ? detector : "rules";
  // Default invocation: `uv run contig eval-detector --json` from the repo root.
  // Override with CONTIG_CMD (e.g. "contig") if the CLI is on PATH directly.
  const override = process.env.CONTIG_CMD;
  const cmd = override ?? "uv";
  const args = (override ? [] : ["run", "contig"]).concat([
    "eval-detector",
    `--detector=${name}`,
    "--json",
  ]);
  try {
    const { stdout } = await pexec(cmd, args, { cwd: repoRoot(), timeout: 30_000 });
    return JSON.parse(stdout) as DetectorEvalReport;
  } catch {
    return null;
  }
}

/** Auto-captured pending-review failure cases (provisional labels awaiting a human). */
export async function getPendingCorpus(): Promise<FailureCase[]> {
  const p = path.join(runsDir(), "pending_corpus.jsonl");
  try {
    const txt = await fs.readFile(p, "utf8");
    return txt
      .split("\n")
      .filter((line) => line.trim().length > 0)
      .map((line) => JSON.parse(line) as FailureCase);
  } catch {
    return [];
  }
}

// --- In-run controls + confirm gate (PRD contracts A, B, C, E) ----------------
// The dashboard never controls a process directly: cancel, resume, and approve
// all shell out to the Python CLI (CONTIG_DISPATCH_CMD), exactly like dispatch.
// The run id is validated (charset, no leading dash) and passed as a positional
// after a "--" terminator, so it can never be smuggled in as a flag.

/** Raised when a run id fails validation (bad charset or a leading dash). */
export class InvalidRunIdError extends Error {}

/** Raised when a control action (cancel/resume/approve) fails at the CLI. */
export class RunControlError extends Error {}

/**
 * A run id is a safe filesystem token: letters, digits, dot, underscore, and
 * dash, with no leading dash. This is the same guard the corpus-promote path
 * uses, and it keeps the value from ever being parsed as a CLI option.
 */
function isSafeRunId(value: string): boolean {
  return (
    typeof value === "string" &&
    value.length > 0 &&
    /^[A-Za-z0-9._-]+$/.test(value) &&
    !value.startsWith("-")
  );
}

/**
 * Run a `contig` subcommand for a single run id, shelling out via the same
 * CONTIG_DISPATCH_CMD base the dispatch routes use. The run id is validated and
 * passed as a positional after "--"; extra flags (already trusted, e.g.
 * --reject) are passed before the terminator. Throws InvalidRunIdError on a bad
 * id and RunControlError if the CLI exits non-zero.
 */
async function runControlCommand(
  subcommand: string,
  id: string,
  flags: string[] = [],
): Promise<void> {
  if (!isSafeRunId(id)) {
    throw new InvalidRunIdError(`Invalid run id: ${id}`);
  }
  const base = (process.env.CONTIG_DISPATCH_CMD ?? "uv run contig").split(" ");
  const args = [
    ...base.slice(1),
    subcommand,
    `--runs-dir=${runsDir()}`,
    ...flags,
    "--",
    id,
  ];
  try {
    await pexec(base[0], args, { cwd: repoRoot(), timeout: 30_000 });
  } catch (err) {
    const stderr = (err as { stderr?: string })?.stderr;
    throw new RunControlError(
      typeof stderr === "string" && stderr.trim().length > 0
        ? stderr.trim()
        : `contig ${subcommand} failed for ${id}.`,
    );
  }
}

/**
 * Cancel an active run: shell `contig cancel <id>`, which sends SIGTERM to the
 * run's process group and writes status.json state "cancelled". Throws if the id
 * is invalid or the run is not active (the CLI exits non-zero).
 */
export async function cancelRun(id: string): Promise<void> {
  await runControlCommand("cancel", id);
}

/**
 * Resume a cancelled or interrupted run: shell `contig resume <id>`, which
 * re-runs the SAME run id in the SAME run dir with Nextflow -resume so cached
 * tasks are reused. Throws if the id is invalid or the run cannot be resumed.
 */
export async function resumeRun(id: string): Promise<void> {
  await runControlCommand("resume", id);
}

/**
 * Approve or reject the decision a paused run is waiting on: shell `contig approve
 * <id>` (with --reject for a rejection), which writes runs/<id>/approval.json so
 * the engine's poll unblocks. For a guided-escalation choice (PRD contract D), a
 * non-negative integer choice picks the ranked option and is passed as
 * `--choose=<n>`, so the engine applies options[n]. The choice is meaningful only
 * on an approve; a reject ignores it. Throws if the id is invalid or the CLI fails.
 */
export async function decideApproval(
  id: string,
  decision: "approve" | "reject",
  choice?: number,
): Promise<void> {
  const flags: string[] = [];
  if (decision === "reject") {
    flags.push("--reject");
  } else if (typeof choice === "number") {
    // The index is validated at the route boundary (a non-negative integer within
    // the options length); guard again here so a malformed value never reaches the
    // CLI as anything but a plain --choose=<n>.
    if (!Number.isInteger(choice) || choice < 0) {
      throw new InvalidRunIdError(`Invalid choice index: ${choice}`);
    }
    flags.push(`--choose=${choice}`);
  }
  await runControlCommand("approve", id, flags);
}

/**
 * The patch a paused run is waiting on (runs/<id>/pending_approval.json), or null
 * if nothing is pending. The awaiting_approval view reads this to render the
 * proposed patch with Approve and Reject.
 */
export async function getPendingApproval(
  id: string,
): Promise<PendingApproval | null> {
  const p = path.join(runsDir(), id, "pending_approval.json");
  try {
    return JSON.parse(await fs.readFile(p, "utf8")) as PendingApproval;
  } catch {
    return null;
  }
}

// --- Eval history (PRD contract D) --------------------------------------------
// The engine appends one EvalSnapshot per line to src/contig/data/eval_history.jsonl
// on `eval-detector --snapshot` and on corpus-promote. The /eval trend reads the
// whole file to plot accuracy over time and per-class deltas.

/** Absolute path to the committed eval-history file (CONTIG_EVAL_HISTORY override). */
function evalHistoryPath(): string {
  return process.env.CONTIG_EVAL_HISTORY
    ? path.resolve(process.env.CONTIG_EVAL_HISTORY)
    : path.resolve(repoRoot(), "src", "contig", "data", "eval_history.jsonl");
}

/**
 * Every eval snapshot on disk, in file order (oldest first). Malformed lines are
 * skipped (a half-written final line never breaks the trend). Returns an empty
 * array when the history file is absent, so the page degrades gracefully.
 */
export async function getEvalHistory(): Promise<EvalSnapshot[]> {
  let txt: string;
  try {
    txt = await fs.readFile(evalHistoryPath(), "utf8");
  } catch {
    return [];
  }
  const out: EvalSnapshot[] = [];
  for (const line of txt.split("\n")) {
    if (line.trim().length === 0) continue;
    try {
      out.push(JSON.parse(line) as EvalSnapshot);
    } catch {
      // Skip a malformed or half-written line; the rest of the history is valid.
    }
  }
  return out;
}

// --- Notifications (PRD contract A) --------------------------------------------
// The engine appends one JSON line per lifecycle event to
// <runsDir>/notifications.jsonl: {ts, run_id, kind, message} with kind one of
// finished | failed | cancelled | awaiting_approval. The header bell reads the
// whole file (newest first) into an activity panel; an awaiting_approval event
// links to its run so a paused run can be resolved.

/** The kinds the notifications feed knows how to render (PRD contract A). */
const NOTIFICATION_KINDS = new Set([
  "finished",
  "failed",
  "cancelled",
  "awaiting_approval",
]);

/** Whether a parsed line is a well-formed NotificationEvent we can render. */
function isNotificationEvent(value: unknown): value is NotificationEvent {
  if (typeof value !== "object" || value === null) return false;
  const e = value as Record<string, unknown>;
  return (
    typeof e.ts === "string" &&
    typeof e.run_id === "string" &&
    typeof e.kind === "string" &&
    NOTIFICATION_KINDS.has(e.kind) &&
    typeof e.message === "string"
  );
}

/**
 * Recent lifecycle events from <runsDir>/notifications.jsonl, newest first. A
 * missing file (no run has emitted yet) yields an empty list, not an error.
 * Malformed or half-written lines are skipped, and lines that do not match the
 * pinned shape are dropped so the panel only ever renders known event kinds.
 * `limit` caps how many of the newest events are returned.
 */
export async function getNotifications(limit = 30): Promise<NotificationEvent[]> {
  const p = path.join(runsDir(), "notifications.jsonl");
  let txt: string;
  try {
    txt = await fs.readFile(p, "utf8");
  } catch {
    return [];
  }
  const events: NotificationEvent[] = [];
  for (const line of txt.split("\n")) {
    if (line.trim().length === 0) continue;
    try {
      const parsed = JSON.parse(line) as unknown;
      if (isNotificationEvent(parsed)) events.push(parsed);
    } catch {
      // A half-written final line (the engine appends concurrently) is ignored.
    }
  }
  // Newest first: the file is append-order (oldest first), so reverse and cap.
  events.reverse();
  return events.slice(0, limit);
}

// --- Output integrity (PRD contract B) -----------------------------------------
// `contig verify <id> --json` re-hashes a run's recorded output files against the
// checksums in run_record.json and reports {ok, changed, missing}. The run detail
// page shows a badge: outputs verified (ok), drift detected (changed/missing), or
// not captured (the run recorded no output checksums, so there is nothing to
// verify). The dashboard never re-hashes itself; integrity stays in the engine.

/**
 * Verify a run's outputs by shelling out to `contig verify <id> --json`. The run
 * id is validated (same guard as the control commands) and passed as a positional
 * after a "--" terminator, so it can never be parsed as a flag. Returns the parsed
 * {ok, changed, missing} report, or null if the CLI is unavailable or its output
 * is unparseable (the page then degrades to a neutral, not-captured state). A
 * non-zero exit on drift still carries JSON on stdout, so we read that too.
 */
export async function getOutputVerification(
  id: string,
): Promise<OutputVerification | null> {
  if (!isSafeRunId(id)) throw new InvalidRunIdError(`Invalid run id: ${id}`);
  const base = (process.env.CONTIG_DISPATCH_CMD ?? "uv run contig").split(" ");
  const args = [
    ...base.slice(1),
    "verify",
    `--runs-dir=${runsDir()}`,
    "--json",
    "--",
    id,
  ];
  // `contig verify` exits non-zero on drift, but still prints the JSON report on
  // stdout, so we parse stdout whether the call resolved or rejected.
  function parse(stdout: unknown): OutputVerification | null {
    if (typeof stdout !== "string") return null;
    try {
      const data = JSON.parse(stdout) as OutputVerification;
      if (
        typeof data.ok === "boolean" &&
        Array.isArray(data.changed) &&
        Array.isArray(data.missing)
      ) {
        // The signed-record fields are present only when the run carries a
        // signature.json (PRD contract E). Keep them only when they are real
        // booleans so the badge never reads a half-formed value as signed.
        const out: OutputVerification = {
          ok: data.ok,
          changed: data.changed,
          missing: data.missing,
        };
        if (typeof data.signed === "boolean") out.signed = data.signed;
        if (typeof data.signature_ok === "boolean") {
          out.signature_ok = data.signature_ok;
        }
        return out;
      }
    } catch {
      return null;
    }
    return null;
  }
  try {
    const { stdout } = await pexec(base[0], args, {
      cwd: repoRoot(),
      timeout: 30_000,
    });
    return parse(stdout);
  } catch (err) {
    return parse((err as { stdout?: string })?.stdout);
  }
}

// --- Resource cost (PRD contract B) --------------------------------------------
// `contig cost <id> --json` applies the configured rates to the resource_usage
// recorded in run_record.json and reports {currency, rate_cpu_hour,
// rate_mem_gb_hour, total, by_task}. Rates default to 0 (local compute is free),
// so the default total is 0; a caller may pass rates to get a real estimate. The
// run detail card reads this for the total, and reads resource_usage off the
// record directly for the per-task duration/memory rows.

/** A non-negative rate string safe to pass to the CLI (no leading dash, plain number). */
function isSafeRate(value: string): boolean {
  return /^[0-9]+(\.[0-9]+)?$/.test(value);
}

/**
 * The cost report for a run by shelling out to `contig cost <id> --json` (the
 * cost model lives in the engine). The run id is validated (same guard as the
 * control commands) and passed as a positional after a "--" terminator, so it can
 * never be parsed as a flag; the optional rates are validated as plain numbers
 * and passed as --opt=value. Returns null if the CLI is unavailable or its output
 * is unparseable, so the card can degrade gracefully. Rates default to 0 (free).
 */
export async function getRunCost(
  id: string,
  rates?: { cpuHour?: string; memGbHour?: string; currency?: string },
): Promise<CostReport | null> {
  if (!isSafeRunId(id)) throw new InvalidRunIdError(`Invalid run id: ${id}`);
  const base = (process.env.CONTIG_DISPATCH_CMD ?? "uv run contig").split(" ");
  const extra: string[] = [];
  if (rates?.cpuHour && isSafeRate(rates.cpuHour)) {
    extra.push(`--rate-cpu-hour=${rates.cpuHour}`);
  }
  if (rates?.memGbHour && isSafeRate(rates.memGbHour)) {
    extra.push(`--rate-mem-gb-hour=${rates.memGbHour}`);
  }
  if (rates?.currency && /^[A-Za-z]{1,5}$/.test(rates.currency)) {
    extra.push(`--currency=${rates.currency}`);
  }
  const args = [
    ...base.slice(1),
    "cost",
    `--runs-dir=${runsDir()}`,
    "--json",
    ...extra,
    "--",
    id,
  ];
  function parse(stdout: unknown): CostReport | null {
    if (typeof stdout !== "string") return null;
    try {
      const data = JSON.parse(stdout) as CostReport;
      if (
        typeof data.total === "number" &&
        typeof data.currency === "string" &&
        Array.isArray(data.by_task)
      ) {
        return data;
      }
    } catch {
      return null;
    }
    return null;
  }
  try {
    const { stdout } = await pexec(base[0], args, {
      cwd: repoRoot(),
      timeout: 30_000,
    });
    return parse(stdout);
  } catch (err) {
    return parse((err as { stdout?: string })?.stdout);
  }
}

// --- Pre-run estimate (PRD contract B) -----------------------------------------
// `contig estimate --pipeline X --input <sheet> --json` derives a runtime and
// cost estimate from prior FINISHED runs of the same pipeline (data-driven), or a
// transparent heuristic when there is no history. The estimate model lives in the
// engine; the dashboard shells out and shows the figures on the launch form before
// a run starts. The pipeline is constrained to the known set and the sheet path is
// validated (exists, no leading dash), both passed as --opt=value, so there is no
// flag-smuggling surface.

/** Raised when an estimate request is invalid (unknown pipeline or bad sheet path). */
export class EstimateValidationError extends Error {}

/**
 * A pre-run estimate by shelling out to `contig estimate --json`. The pipeline is
 * checked against the known set and the sample sheet is validated as a real file
 * (same guard as dispatch); both pass as --opt=value. Optional rates (validated as
 * plain numbers) and a currency pass as --opt=value so a real cost figure can be
 * shown. Returns the parsed EstimateReport, or null if the CLI is unavailable or
 * its output is unparseable, so the launch form degrades gracefully. Throws
 * EstimateValidationError on an unknown pipeline or a missing sheet.
 */
export async function getEstimate(req: {
  pipeline: string;
  input: string;
  rateCpuHour?: string;
  rateMemGbHour?: string;
  currency?: string;
}): Promise<EstimateReport | null> {
  if (!KNOWN_PIPELINES.has(req.pipeline)) {
    throw new EstimateValidationError("Unknown pipeline.");
  }
  let input: string;
  try {
    input = await assertFile(req.input, "Sample sheet");
  } catch {
    throw new EstimateValidationError("Sample sheet not found.");
  }
  const base = (process.env.CONTIG_DISPATCH_CMD ?? "uv run contig").split(" ");
  const extra: string[] = [];
  if (req.rateCpuHour && isSafeRate(req.rateCpuHour)) {
    extra.push(`--rate-cpu-hour=${req.rateCpuHour}`);
  }
  if (req.rateMemGbHour && isSafeRate(req.rateMemGbHour)) {
    extra.push(`--rate-mem-gb-hour=${req.rateMemGbHour}`);
  }
  if (req.currency && /^[A-Za-z]{1,5}$/.test(req.currency)) {
    extra.push(`--currency=${req.currency}`);
  }
  const args = [
    ...base.slice(1),
    "estimate",
    `--pipeline=${req.pipeline}`,
    `--input=${input}`,
    `--runs-dir=${runsDir()}`,
    "--json",
    ...extra,
  ];
  function parse(stdout: unknown): EstimateReport | null {
    if (typeof stdout !== "string") return null;
    try {
      const data = JSON.parse(stdout) as EstimateReport;
      if (
        (data.basis === "history" || data.basis === "heuristic") &&
        typeof data.est_runtime_sec === "number" &&
        typeof data.est_cost === "number" &&
        typeof data.currency === "string"
      ) {
        return data;
      }
    } catch {
      return null;
    }
    return null;
  }
  try {
    const { stdout } = await pexec(base[0], args, {
      cwd: repoRoot(),
      timeout: 30_000,
    });
    return parse(stdout);
  } catch (err) {
    return parse((err as { stdout?: string })?.stdout);
  }
}

// --- Provenance export (PRD contract C) ----------------------------------------
// `contig export <id> --rocrate` prints an RO-Crate ro-crate-metadata.json and
// `contig methods <id>` prints a deterministic, citation-ready methods paragraph.
// Both are offline (no LLM, no network) and live in the engine; the dashboard
// shells out and serves the bytes for download. The run id is validated and passed
// as a positional after a "--" terminator, so it can never be parsed as a flag.

/**
 * The RO-Crate JSON for a run by shelling out to `contig export <id> --rocrate`.
 * Returns the raw JSON string (already serialized by the engine) so the route can
 * serve it byte for byte, or null if the CLI is unavailable. The run id is
 * validated and passed as a positional after "--".
 */
export async function getRunRoCrate(id: string): Promise<string | null> {
  if (!isSafeRunId(id)) throw new InvalidRunIdError(`Invalid run id: ${id}`);
  const base = (process.env.CONTIG_DISPATCH_CMD ?? "uv run contig").split(" ");
  const args = [
    ...base.slice(1),
    "export",
    `--runs-dir=${runsDir()}`,
    "--rocrate",
    "--",
    id,
  ];
  try {
    const { stdout } = await pexec(base[0], args, {
      cwd: repoRoot(),
      timeout: 30_000,
    });
    return typeof stdout === "string" && stdout.trim().length > 0 ? stdout : null;
  } catch {
    return null;
  }
}

/**
 * The methods paragraph for a run by shelling out to `contig methods <id>`.
 * Returns the plain-text paragraph, or null if the CLI is unavailable. The run id
 * is validated and passed as a positional after "--".
 */
export async function getRunMethods(id: string): Promise<string | null> {
  if (!isSafeRunId(id)) throw new InvalidRunIdError(`Invalid run id: ${id}`);
  const base = (process.env.CONTIG_DISPATCH_CMD ?? "uv run contig").split(" ");
  const args = [
    ...base.slice(1),
    "methods",
    `--runs-dir=${runsDir()}`,
    "--",
    id,
  ];
  try {
    const { stdout } = await pexec(base[0], args, {
      cwd: repoRoot(),
      timeout: 30_000,
    });
    return typeof stdout === "string" && stdout.trim().length > 0 ? stdout : null;
  } catch {
    return null;
  }
}

/**
 * The self-contained shareable HTML report for a run by shelling out to `contig
 * show <id> --html` (PRD contract D). The report is rendered offline by the engine
 * (no scripts, no network, fully escaped, print-to-PDF friendly); this returns the
 * raw HTML string so the route can serve it byte for byte, or null if the CLI is
 * unavailable. The run id is validated and passed as a positional after "--".
 */
export async function getRunReportHtml(id: string): Promise<string | null> {
  if (!isSafeRunId(id)) throw new InvalidRunIdError(`Invalid run id: ${id}`);
  const base = (process.env.CONTIG_DISPATCH_CMD ?? "uv run contig").split(" ");
  const args = [
    ...base.slice(1),
    "show",
    `--runs-dir=${runsDir()}`,
    "--html",
    "--",
    id,
  ];
  try {
    const { stdout } = await pexec(base[0], args, {
      cwd: repoRoot(),
      timeout: 30_000,
    });
    return typeof stdout === "string" && stdout.trim().length > 0 ? stdout : null;
  } catch {
    return null;
  }
}

// --- Cross-run benchmark (PRD contract A) --------------------------------------
// `contig benchmark <id> --json` compares a run against the designated reference
// for its (pipeline, assay) by QC metric values within a relative tolerance plus
// structural shape, robust to run-to-run non-determinism. The comparison model
// lives in the engine; the dashboard shells out and renders run vs reference per
// metric. The run id is validated and passed as a positional after a "--"
// terminator, and the optional tolerance is validated as a plain number and passed
// as --opt=value, so there is no flag-smuggling surface. No reference recorded for
// the run's pipeline/assay yields status "no_reference", a clear state, not an error.

/** A tolerance string safe to pass to the CLI (a plain non-negative number, no leading dash). */
function isSafeTolerance(value: string): boolean {
  return /^[0-9]+(\.[0-9]+)?$/.test(value);
}

/**
 * The cross-run benchmark for a run by shelling out to `contig benchmark <id>
 * --json` (PRD contract A). The run id is validated (same guard as the control
 * commands) and passed as a positional after a "--" terminator; the optional
 * tolerance is validated and passed as --opt=value. Returns the parsed report, or
 * null if the CLI is unavailable or its output is unparseable, so the benchmark
 * section can degrade gracefully. A "no_reference" status is a normal, parseable
 * report (no reference set), not a failure, and is returned as-is.
 */
export async function getBenchmark(
  id: string,
  tolerance?: string,
): Promise<BenchmarkReport | null> {
  if (!isSafeRunId(id)) throw new InvalidRunIdError(`Invalid run id: ${id}`);
  const base = (process.env.CONTIG_DISPATCH_CMD ?? "uv run contig").split(" ");
  const extra: string[] = [];
  if (tolerance && isSafeTolerance(tolerance)) {
    extra.push(`--tolerance=${tolerance}`);
  }
  const args = [
    ...base.slice(1),
    "benchmark",
    `--runs-dir=${runsDir()}`,
    "--json",
    ...extra,
    "--",
    id,
  ];
  function parse(stdout: unknown): BenchmarkReport | null {
    if (typeof stdout !== "string") return null;
    try {
      const data = JSON.parse(stdout) as BenchmarkReport;
      if (
        (data.status === "match" ||
          data.status === "drift" ||
          data.status === "no_reference") &&
        typeof data.tolerance === "number" &&
        typeof data.matched === "number" &&
        typeof data.drifted === "number" &&
        Array.isArray(data.checks)
      ) {
        return data;
      }
    } catch {
      return null;
    }
    return null;
  }
  try {
    const { stdout } = await pexec(base[0], args, {
      cwd: repoRoot(),
      timeout: 30_000,
    });
    return parse(stdout);
  } catch (err) {
    return parse((err as { stdout?: string })?.stdout);
  }
}

// --- Failure clustering + corpus coverage (PRD contracts B, C) ------------------
// `contig clusters --json` groups corpus and pending cases by failure class plus a
// normalized log signature, worst first; `contig coverage --json` reports per-class
// support, the thin classes (fewer than 3 cases), the by-source breakdown, and a
// confirmed-over-time series. Both read the corpus only (no run id, no network) and
// the analysis lives in the engine; the dashboard shells out and renders the views.

/**
 * The failure clusters by shelling out to `contig clusters --json` (PRD contract
 * B), already ordered worst first by the engine. Returns the parsed list, or null
 * if the CLI is unavailable or its output is unparseable, so the clusters view can
 * degrade gracefully. An empty corpus is an empty array (a valid, parseable
 * result), not null.
 */
export async function getClusters(): Promise<FailureCluster[] | null> {
  const override = process.env.CONTIG_CMD;
  const cmd = override ?? "uv";
  const args = (override ? [] : ["run", "contig"]).concat(["clusters", "--json"]);
  try {
    const { stdout } = await pexec(cmd, args, { cwd: repoRoot(), timeout: 30_000 });
    const data = JSON.parse(stdout) as unknown;
    if (!Array.isArray(data)) return null;
    return data.filter(
      (c): c is FailureCluster =>
        typeof c === "object" &&
        c !== null &&
        typeof (c as FailureCluster).failure_class === "string" &&
        typeof (c as FailureCluster).count === "number" &&
        Array.isArray((c as FailureCluster).case_ids),
    );
  } catch {
    return null;
  }
}

/**
 * The corpus coverage report by shelling out to `contig coverage --json` (PRD
 * contract C). Returns the parsed report, or null if the CLI is unavailable or its
 * output is unparseable, so the coverage panel can degrade gracefully.
 */
export async function getCoverage(): Promise<CoverageReport | null> {
  const override = process.env.CONTIG_CMD;
  const cmd = override ?? "uv";
  const args = (override ? [] : ["run", "contig"]).concat(["coverage", "--json"]);
  try {
    const { stdout } = await pexec(cmd, args, { cwd: repoRoot(), timeout: 30_000 });
    const data = JSON.parse(stdout) as CoverageReport;
    if (
      typeof data.total === "number" &&
      typeof data.per_class === "object" &&
      data.per_class !== null &&
      Array.isArray(data.thin) &&
      typeof data.by_source === "object" &&
      data.by_source !== null
    ) {
      return data;
    }
    return null;
  } catch {
    return null;
  }
}

// --- Per-user run isolation (PRD contract E) -----------------------------------
// A dispatch route tags each run with its owner by writing runs/<id>/owner.json
// {owner, email}. listRuns and getRun filter by the current viewer: a user sees
// only their own runs; an admin sees all; a run with no owner.json (a CLI launch)
// is admin-only. Under the auth bypass the viewer is a synthetic local admin, so
// local dev and the e2e suite see everything. Ownership lives entirely here in
// the dashboard; the engine is unchanged. The pure rule (canViewRun,
// filterOwnedRunIds, Viewer) is re-exported from lib/ownership.ts above.

/** The owner tag a run carries (runs/<id>/owner.json), or null if it has none. */
export async function getRunOwner(id: string): Promise<RunOwner | null> {
  const p = path.join(runsDir(), id, "owner.json");
  try {
    const data = JSON.parse(await fs.readFile(p, "utf8")) as RunOwner;
    if (typeof data.owner === "string") return data;
    return null;
  } catch {
    return null;
  }
}

/**
 * Write runs/<id>/owner.json for a freshly dispatched run. Best effort: a failure
 * to record the owner never blocks the launch (the run still ran), it only means
 * the run is admin-only until tagged. Called by the dispatch routes after spawn.
 */
export async function writeRunOwner(id: string, owner: RunOwner): Promise<void> {
  const dir = path.join(runsDir(), id);
  try {
    await fs.mkdir(dir, { recursive: true });
    await fs.writeFile(
      path.join(dir, "owner.json"),
      JSON.stringify(owner, null, 2),
      "utf8",
    );
  } catch {
    // Recording the owner is best effort; the run itself is unaffected.
  }
}

