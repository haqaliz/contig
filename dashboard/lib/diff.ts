// Pure, client-safe run comparison. Given two RunRecord objects (run a vs run b),
// this produces a structured diff so the dashboard can answer the reproducibility
// question: "did my re-run reproduce, and if not, what changed?". No fs, no Node
// modules, so this is safe to import from server or client components.
//
// All trust logic stays in the engine: we read the serialized verdict and the
// recorded pins straight off each record and only describe how they differ.
import type { QCStatus, RunRecord, Verdict } from "./types";
import { taskCounts } from "./derive";

/** Whether the two sides of a comparison match, and how a row differs. */
export type DiffState = "same" | "changed" | "added" | "removed";

/** A single field compared across two runs (e.g. pipeline, revision). */
export interface ScalarDiff {
  label: string;
  a: string;
  b: string;
  state: "same" | "changed";
}

/** One key compared across two maps (parameters, checksums, digests). */
export interface MapEntryDiff {
  key: string;
  /** Value on run a, or null when the key is absent on a. */
  a: string | null;
  /** Value on run b, or null when the key is absent on b. */
  b: string | null;
  state: DiffState;
}

/** A whole map (parameters, input/output checksums, container digests) diffed. */
export interface MapDiff {
  entries: MapEntryDiff[];
  /** True when every key is present on both sides with an equal value. */
  identical: boolean;
  /** Count of entries that are not "same". */
  changedCount: number;
}

/** Task totals compared (mirror of taskCounts), with a same/changed verdict. */
export interface TaskCountDiff {
  a: { total: number; failed: number };
  b: { total: number; failed: number };
  state: "same" | "changed";
}

/** One QC check compared across the two runs, keyed by check name. */
export interface QcEntryDiff {
  check: string;
  /** Value/status on run a, null when the check is absent on a. */
  a: { status: QCStatus; value: number | null } | null;
  /** Value/status on run b, null when the check is absent on b. */
  b: { status: QCStatus; value: number | null } | null;
  state: DiffState;
}

/** The full QC comparison, keyed by check name. */
export interface QcDiff {
  entries: QcEntryDiff[];
  identical: boolean;
  changedCount: number;
}

/** The complete structured diff between run a and run b. */
export interface RunDiff {
  idA: string;
  idB: string;
  verdict: { a: Verdict; b: Verdict; state: "same" | "changed" };
  pipeline: ScalarDiff;
  revision: ScalarDiff;
  parameters: MapDiff;
  containerDigests: MapDiff;
  inputChecksums: MapDiff;
  outputChecksums: MapDiff;
  taskCounts: TaskCountDiff;
  qc: QcDiff;
  /** True when nothing of substance differs: a clean reproduction. */
  reproduced: boolean;
}

// Stable string form of a parameter/checksum value, so object params compare
// deterministically and primitives read cleanly.
function asString(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function scalarDiff(label: string, a: string, b: string): ScalarDiff {
  return { label, a, b, state: a === b ? "same" : "changed" };
}

// Diff two record-shaped maps key by key. Keys are unioned and sorted so the
// output is stable regardless of insertion order.
function mapDiff(
  a: Record<string, unknown>,
  b: Record<string, unknown>,
): MapDiff {
  const keys = Array.from(
    new Set([...Object.keys(a), ...Object.keys(b)]),
  ).sort();

  const entries: MapEntryDiff[] = keys.map((key) => {
    const hasA = Object.prototype.hasOwnProperty.call(a, key);
    const hasB = Object.prototype.hasOwnProperty.call(b, key);
    const va = hasA ? asString(a[key]) : null;
    const vb = hasB ? asString(b[key]) : null;

    let state: DiffState;
    if (hasA && !hasB) state = "removed";
    else if (!hasA && hasB) state = "added";
    else if (va === vb) state = "same";
    else state = "changed";

    return { key, a: va, b: vb, state };
  });

  const changedCount = entries.filter((e) => e.state !== "same").length;
  return { entries, identical: changedCount === 0, changedCount };
}

function qcDiff(a: RunRecord, b: RunRecord): QcDiff {
  const byCheckA = new Map(a.qc_results.map((q) => [q.check, q]));
  const byCheckB = new Map(b.qc_results.map((q) => [q.check, q]));
  const checks = Array.from(
    new Set([...byCheckA.keys(), ...byCheckB.keys()]),
  ).sort();

  const entries: QcEntryDiff[] = checks.map((check) => {
    const qa = byCheckA.get(check);
    const qb = byCheckB.get(check);
    const sideA = qa ? { status: qa.status, value: qa.value } : null;
    const sideB = qb ? { status: qb.status, value: qb.value } : null;

    let state: DiffState;
    if (sideA && !sideB) state = "removed";
    else if (!sideA && sideB) state = "added";
    else if (sideA && sideB && sideA.status === sideB.status && sideA.value === sideB.value)
      state = "same";
    else state = "changed";

    return { check, a: sideA, b: sideB, state };
  });

  const changedCount = entries.filter((e) => e.state !== "same").length;
  return { entries, identical: changedCount === 0, changedCount };
}

/**
 * Compare two runs and return a structured, render-ready diff. The result is the
 * single source the compare page reads from, so the page never re-derives trust
 * or reproduction logic itself.
 */
export function diffRuns(a: RunRecord, b: RunRecord): RunDiff {
  const verdict = {
    a: a.verdict,
    b: b.verdict,
    state: (a.verdict === b.verdict ? "same" : "changed") as "same" | "changed",
  };
  const pipeline = scalarDiff("Pipeline", a.pipeline, b.pipeline);
  const revision = scalarDiff("Revision", a.pipeline_revision, b.pipeline_revision);
  const parameters = mapDiff(a.parameters, b.parameters);
  const containerDigests = mapDiff(a.container_digests, b.container_digests);
  const inputChecksums = mapDiff(a.input_checksums, b.input_checksums);
  const outputChecksums = mapDiff(a.output_checksums, b.output_checksums);

  const ca = taskCounts(a);
  const cb = taskCounts(b);
  const tasks: TaskCountDiff = {
    a: ca,
    b: cb,
    state: ca.total === cb.total && ca.failed === cb.failed ? "same" : "changed",
  };

  const qc = qcDiff(a, b);

  // A clean reproduction: same verdict, same pipeline+revision, and every map and
  // QC check matches. Task counts must match too.
  const reproduced =
    verdict.state === "same" &&
    pipeline.state === "same" &&
    revision.state === "same" &&
    parameters.identical &&
    containerDigests.identical &&
    inputChecksums.identical &&
    outputChecksums.identical &&
    tasks.state === "same" &&
    qc.identical;

  return {
    idA: a.run_id,
    idB: b.run_id,
    verdict,
    pipeline,
    revision,
    parameters,
    containerDigests,
    inputChecksums,
    outputChecksums,
    taskCounts: tasks,
    qc,
    reproduced,
  };
}
