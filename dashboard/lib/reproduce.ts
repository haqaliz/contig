// Server-side disk access to the engine's third-party `contig reproduce`
// bundles (C8). The sibling lib/runs.ts reads first-party run bundles; a
// reproduce bundle is a directory under the SAME runs directory carrying
// reproduce_record.json (NOT run_record.json), so the first-party list skips it
// and only /reproduce renders it. The pure derivations (overall status, labels,
// counts) live in lib/reproduce-derive.ts without a server-only guard, so they
// are unit-observable.
//
// "server-only" guards against importing this into a client component by mistake.
import "server-only";

import { promises as fs } from "fs";
import { existsSync } from "fs";
import path from "path";

import { runsDir } from "./runs";
import type {
  ReproduceManifest,
  ReproduceRecord,
  ReproduceSignature,
} from "./types";

/**
 * One reproduce bundle record by id (runs/<id>/reproduce_record.json), or null
 * when absent or malformed -- the listing skips it, never crashes (mirror of
 * readRecord in lib/runs.ts).
 */
export async function readReproduceRecord(
  id: string,
): Promise<ReproduceRecord | null> {
  const p = path.join(runsDir(), id, "reproduce_record.json");
  try {
    return JSON.parse(await fs.readFile(p, "utf8")) as ReproduceRecord;
  } catch {
    return null;
  }
}

/**
 * One reproduce bundle's re-runnable manifest (runs/<id>/reproduce.json), or
 * null when absent or malformed.
 */
export async function readReproduceManifest(
  id: string,
): Promise<ReproduceManifest | null> {
  const p = path.join(runsDir(), id, "reproduce.json");
  try {
    return JSON.parse(await fs.readFile(p, "utf8")) as ReproduceManifest;
  } catch {
    return null;
  }
}

/**
 * Every reproduce bundle on disk, newest first (created_at desc; ISO strings
 * sort lexically). Directories without a reproduce_record.json are skipped
 * (mirror of listRuns's skip-without-record semantics); a malformed record is
 * skipped too. An unreadable runs directory yields an empty list, not an error.
 */
export async function listReproduceRuns(): Promise<ReproduceRecord[]> {
  let entries: string[];
  try {
    entries = await fs.readdir(runsDir());
  } catch {
    return [];
  }
  const records = await Promise.all(
    entries.map((name) => readReproduceRecord(name)),
  );
  const present = records.filter((r): r is ReproduceRecord => r !== null);
  present.sort((a, b) => b.created_at.localeCompare(a.created_at));
  return present;
}

/** Absolute path to a reproduce bundle's directory. */
export function reproduceBundlePath(id: string): string {
  return path.join(runsDir(), id);
}

/**
 * One raw bundle file's bytes (reproduce_record.json / reproduce.json /
 * signature.json) for the download route, or null when absent. Callers pick
 * the name from an allowlist; the path is runtime-scoped (env or cwd), never
 * part of the bundle.
 */
export async function readReproduceBundleFile(
  id: string,
  name: string,
): Promise<Buffer | null> {
  try {
    return await fs.readFile(path.join(reproduceBundlePath(id), name));
  } catch (err) {
    if ((err as NodeJS.ErrnoException).code === "ENOENT") {
      return null;
    }
    throw err;
  }
}

/**
 * A reproduce bundle's detached signature sidecar (signature.json), or null
 * when absent or malformed. Rendered as presence plus algo and the public-key
 * fingerprint; the dashboard never verifies the signature (PRD N1 defers it).
 */
export async function readReproduceSignature(
  id: string,
): Promise<ReproduceSignature | null> {
  const p = path.join(runsDir(), id, "signature.json");
  try {
    return JSON.parse(await fs.readFile(p, "utf8")) as ReproduceSignature;
  } catch {
    return null;
  }
}

/** Whether the bundle carries a detached signature sidecar (signature.json). */
export async function hasSignature(id: string): Promise<boolean> {
  return existsSync(path.join(runsDir(), id, "signature.json"));
}