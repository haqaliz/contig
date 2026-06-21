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
