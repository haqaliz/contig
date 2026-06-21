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
  const args = (override ? [] : ["run", "contig"]).concat([
    "corpus-promote",
    caseId,
    "--pending",
    path.join(runsDir(), "pending_corpus.jsonl"),
  ]);
  if (label) args.push("--label", label);
  await pexec(cmd, args, { cwd: repoRoot(), timeout: 30_000 });
}

/** Raised when a run is already in flight (v1 allows one at a time). */
export class DispatchBusyError extends Error {
  constructor(public readonly runningId: string) {
    super(`A run is already in progress: ${runningId}`);
    this.name = "DispatchBusyError";
  }
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

