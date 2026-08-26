import { test, expect } from "@playwright/test";

import {
  claimCountsLine,
  claimStatusLabel,
  deriveReproduceOverall,
  REPRODUCE_STATUS_ORDER,
} from "../lib/reproduce-derive";
import type { ReproduceClaim } from "../lib/types";

// Unit-level coverage of the pure reproduce derivations (spec A2 / PRD R2):
// the worst-of overall rule pinned for EVERY ordering case -- empty claims and
// non-zero exit included -- plus the labels and counts line. These run in Node
// (no `page`), exercising the server-only-free module from lib/reproduce-derive
// directly (the lib/ownership.ts precedent). The e2e reproduce-page spec then
// confirms the same rules render in the browser.

function claims(...statuses: string[]): ReproduceClaim[] {
  return statuses.map((status, i) => ({
    id: `c${i}`,
    status,
    claimed: 1,
    observed: 1,
    tolerance: 0.1,
    delta: 0,
    message: "",
  }));
}

test("worst-of over claim statuses: diverged dominates everything", () => {
  const { overall } = deriveReproduceOverall({
    exit_code: 0,
    claim_results: claims("reproduced", "within_tolerance", "unverified", "diverged"),
  });
  expect(overall).toBe("diverged");
});

test("within_tolerance dominates unverified and reproduced", () => {
  const { overall } = deriveReproduceOverall({
    exit_code: 0,
    claim_results: claims("reproduced", "within_tolerance", "unverified"),
  });
  expect(overall).toBe("within_tolerance");
});

test("unverified dominates reproduced (honest, never a pass)", () => {
  const { overall } = deriveReproduceOverall({
    exit_code: 0,
    claim_results: claims("reproduced", "unverified"),
  });
  expect(overall).toBe("unverified");
});

test("all reproduced reads reproduced", () => {
  const { overall } = deriveReproduceOverall({
    exit_code: 0,
    claim_results: claims("reproduced", "reproduced"),
  });
  expect(overall).toBe("reproduced");
});

test("an unknown status literal counts as unverified, never a pass", () => {
  const { overall, counts } = deriveReproduceOverall({
    exit_code: 0,
    claim_results: claims("reproduced", "suspicious"),
  });
  expect(overall).toBe("unverified");
  // The unknown literal is counted under its own key, not dropped or relabeled.
  expect(counts).toEqual({ reproduced: 1, suspicious: 1 });
});

test("a non-zero exit reads did_not_complete, claims still tallied", () => {
  const { overall, counts } = deriveReproduceOverall({
    exit_code: 2,
    claim_results: claims("unverified", "reproduced"),
  });
  expect(overall).toBe("did_not_complete");
  expect(counts).toEqual({ unverified: 1, reproduced: 1 });
});

test("empty claims are an honest unverified non-result", () => {
  const { overall, counts } = deriveReproduceOverall({
    exit_code: 0,
    claim_results: [],
  });
  expect(overall).toBe("unverified");
  expect(counts).toEqual({});
});

test("the severity order is pinned", () => {
  expect(REPRODUCE_STATUS_ORDER).toEqual({
    diverged: 0,
    within_tolerance: 1,
    unverified: 2,
    reproduced: 3,
  });
});

test("claim status labels map the four literals and nothing else", () => {
  expect(claimStatusLabel("reproduced")).toBe("Reproduced");
  expect(claimStatusLabel("within_tolerance")).toBe("Within tolerance");
  expect(claimStatusLabel("diverged")).toBe("Diverged");
  expect(claimStatusLabel("unverified")).toBe("Unverified");
  expect(claimStatusLabel("suspicious")).toBe("Unknown");
});

test("the counts line renders known literals first, unknowns under their key", () => {
  expect(
    claimCountsLine({
      reproduced: 1,
      within_tolerance: 1,
      diverged: 1,
      unverified: 1,
      suspicious: 1,
    }),
  ).toBe("1 reproduced · 1 within tolerance · 1 diverged · 1 unverified · 1 suspicious");
  expect(claimCountsLine({})).toBe("No claims");
});