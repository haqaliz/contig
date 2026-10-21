import { test, expect } from "@playwright/test";

import {
  repairStatsRateLabel,
  repairStatsRateSeries,
} from "../lib/derive";
import type { RepairStatsSnapshot } from "../lib/types";

// Unit-level coverage of the pure repair-stats trend helpers (C2-15). Runs in
// Node, no `page`: the same lib/ownership.ts / reproduce-derive.ts precedent.
// The values here mirror `contig repair-stats --history`: a non-computable rate
// is a real state (nothing scorable), and it must never be plotted as 0%.

function snapshot(
  timestamp: string,
  rate: number | null,
): RepairStatsSnapshot {
  return {
    timestamp,
    contig_version: "0.63.0",
    runs_total: 3,
    analyzable: 3,
    not_analyzable: 0,
    attendance_unknown: 0,
    rate_denominator: 2,
    unattended_completed: 1,
    unattended_completion_rate: rate,
    steps_total: 1,
  };
}

test("the sparkline series keeps chronological order and drops non-computable points", () => {
  const history = [
    snapshot("2026-07-01T00:00:00+00:00", 0.5),
    snapshot("2026-07-02T00:00:00+00:00", null),
    snapshot("2026-07-03T00:00:00+00:00", 0.75),
  ];
  expect(repairStatsRateSeries(history)).toEqual([0.5, 0.75]);
});

test("a non-computable rate is labelled honestly, never as 0%", () => {
  expect(repairStatsRateLabel(null)).toBe("not computable");
  expect(repairStatsRateLabel(0)).toBe("0%");
  expect(repairStatsRateLabel(0.6428571428571429)).toBe("64%");
});
