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
  DetectorEvalReport,
  FailureCase,
  LaunchManifest,
  Plan,
  RepairStepLite,
  RunProgress,
  RunRecord,
  RunStatus,
} from "./types";

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

/** All run bundles found on disk. Directories without a run_record.json are skipped. */
export async function listRuns(): Promise<RunRecord[]> {
  let entries: string[];
  try {
    entries = await fs.readdir(runsDir());
  } catch {
    return [];
  }
  const records = await Promise.all(entries.map((name) => readRecord(name)));
  return records.filter((r): r is RunRecord => r !== null);
}

/** One run bundle by id, or null if absent. */
export async function getRun(id: string): Promise<RunRecord | null> {
  return readRecord(id);
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

export type RunState = "finished" | "running" | "interrupted" | "missing";

/**
 * Resolve a run's state. A "running" marker whose process has died (no bundle)
 * is "interrupted", not a stuck "running": a crashed or cancelled run must not
 * block new dispatches or poll forever.
 */
export async function getRunState(id: string): Promise<RunState> {
  if (await readRecord(id)) return "finished";
  const status = await getRunStatus(id);
  if (!status) return "missing";
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
    if (isLive(st)) out.push({ run_id: name, started_at: st!.started_at });
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

/**
 * The detector eval, obtained by shelling out to `contig eval-detector --json`
 * (the detector is Python, the moat; we never re-implement it in TS). Returns
 * null if the CLI is unavailable, so the page can degrade gracefully.
 */
export async function getDetectorEval(): Promise<DetectorEvalReport | null> {
  // Default invocation: `uv run contig eval-detector --json` from the repo root.
  // Override with CONTIG_CMD (e.g. "contig") if the CLI is on PATH directly.
  const override = process.env.CONTIG_CMD;
  const cmd = override ?? "uv";
  const args = (override ? [] : ["run", "contig"]).concat(["eval-detector", "--json"]);
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

