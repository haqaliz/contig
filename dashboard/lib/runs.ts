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
  Plan,
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

/** Runs that are in flight: a "running" status marker and no bundle yet. */
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
    if (st?.state === "running") out.push({ run_id: name, started_at: st.started_at });
  }
  return out;
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

