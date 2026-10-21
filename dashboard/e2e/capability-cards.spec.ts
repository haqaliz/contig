import { test, expect } from "@playwright/test";

import { triageLedgerSummary } from "../lib/derive";
import { reproduceSummary } from "../lib/reproduce-derive";
import type {
  ReproduceClaim,
  ReproduceRecord,
  TriageLedgerRow,
} from "../lib/types";

// Unit-level coverage of the pure derivations behind the two new summary cards
// (C8 reproduce index, C9 Jev triage ledger). These run in Node (no `page`),
// exercising the server-only-free modules directly, in the style of
// reproduce-derive.spec.ts.

function claim(status: string): ReproduceClaim {
  return {
    id: status,
    status,
    claimed: 1,
    observed: 1,
    tolerance: 0.1,
    delta: 0,
    message: "",
  };
}

function record(
  id: string,
  createdAt: string,
  exitCode = 0,
  statuses: string[] = ["reproduced"],
): ReproduceRecord {
  return {
    reproduce_id: id,
    repo: `example/${id}`,
    run_command: "run.sh",
    claims_sha256: "0".repeat(64),
    claim_results: statuses.map(claim),
    exit_code: exitCode,
    created_at: createdAt,
    interpreter: null,
    tool: "contig",
    repair_history: [],
    source_url: null,
    source_commit: null,
    source_tree_sha256: null,
  };
}

test("reproduce summary counts each derived overall", () => {
  const summary = reproduceSummary([
    record("a", "2026-01-01T00:00:00Z", 0, ["reproduced"]),
    record("b", "2026-01-02T00:00:00Z", 0, ["reproduced", "diverged"]),
    record("c", "2026-01-03T00:00:00Z", 2, ["unverified"]),
    record("d", "2026-01-04T00:00:00Z", 0, []),
  ]);
  expect(summary.total).toBe(4);
  expect(summary.byOverall).toEqual({
    reproduced: 1,
    diverged: 1,
    did_not_complete: 1,
    unverified: 1,
  });
});

test("reproduce summary lists the newest verdicts first, capped", () => {
  const summary = reproduceSummary(
    [
      record("old", "2026-01-01T00:00:00Z"),
      record("new", "2026-01-03T00:00:00Z"),
      record("mid", "2026-01-02T00:00:00Z"),
    ],
    2,
  );
  expect(summary.recent.map((r) => r.id)).toEqual(["new", "mid"]);
});

test("triage ledger summary counts surfaces, modes and skip events", () => {
  const summary = triageLedgerSummary(
    [
      { surface: "qc_anomaly", mode: "shadow", actual: "QC-FAIL: x" },
      { surface: "qc_anomaly", mode: "active", actual: "skipped" },
      { surface: "verify_concordance", mode: "shadow", actual: "pass" },
      // Malformed values are ignored, never guessed into a bucket.
      { surface: 7, mode: null, actual: undefined } as unknown as TriageLedgerRow,
    ],
    2,
  );
  expect(summary.total).toBe(4);
  expect(summary.bySurface).toEqual({ qc_anomaly: 2, verify_concordance: 1 });
  expect(summary.byMode).toEqual({ shadow: 2, active: 1 });
  expect(summary.skipped).toBe(1);
  expect(summary.skippedLines).toBe(2);
});
