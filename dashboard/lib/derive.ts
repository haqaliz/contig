// Pure, client-safe derivations over a RunRecord. Kept separate from lib/runs.ts
// (which is server-only and imports fs/child_process) so client components can
// use these helpers without pulling Node modules into the browser bundle.
import type { RunRecord, Verdict } from "./types";

/** Failed/total task counts derived from a run's events (mirror of RunSummary). */
export function taskCounts(record: RunRecord): { total: number; failed: number } {
  const failed = record.events.filter(
    (e) => e.status.toUpperCase() === "FAILED" || (e.exit !== null && e.exit !== 0),
  ).length;
  return { total: record.events.length, failed };
}

/** Did the run apply any repair? */
export function wasRepaired(record: RunRecord): boolean {
  return record.repair_history.length > 0;
}

/** Severity order for sorting/grouping (fail worst). */
export const VERDICT_ORDER: Record<Verdict, number> = {
  fail: 0,
  warn: 1,
  unverified: 2,
  pass: 3,
};

// The detector's failure classes (mirror of FailureClass in src/contig/models.py).
// Used by the curation UI to correct a provisional label, and to validate input.
export const FAILURE_CLASSES = [
  "oom",
  "time_limit",
  "missing_reference",
  "missing_index",
  "bad_param",
  "container_pull_failed",
  "container_unavailable",
  "conda_solve_failed",
  "platform_unsupported",
  "tool_crash",
  "no_progress",
  "qc_anomaly",
  "unknown",
] as const;
