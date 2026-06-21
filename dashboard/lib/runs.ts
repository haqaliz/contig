// Server-side disk access to the Contig engine's artifacts. This module is the
// single data layer the pages call. It reads run_record.json bundles and the
// corpus JSON directly from the runs directory, and shells out to the Python CLI
// only for the detector eval (the detector is the moat and stays in Python).
//
// "server-only" guards against importing this into a client component by mistake.
import "server-only";

import { promises as fs } from "fs";
import path from "path";
import { execFile } from "child_process";
import { promisify } from "util";

import type { DetectorEvalReport, FailureCase, RunRecord } from "./types";

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

