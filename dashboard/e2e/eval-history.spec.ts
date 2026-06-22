import { test, expect } from "@playwright/test";

// Eval-history trend (PRD feature 3). /eval shows an accuracy-over-time trend
// (inline SVG, no chart dependency) plus a snapshot table with per-class deltas.
// The fixture src/contig/data/eval_history.jsonl carries 3 snapshots, so the
// trend and the delta indicators render. We assert structure and a delta, not
// exact percentages, so the test stays valid if the engine appends more snapshots.

test("the eval page renders the accuracy-over-time trend", async ({ page }) => {
  await page.goto("/eval");

  // The trend section and its inline SVG (labeled for screen readers).
  await expect(
    page.getByRole("heading", { name: "Accuracy over time" }),
  ).toBeVisible();
  await expect(
    page.getByRole("img", { name: "Detector accuracy over time" }),
  ).toBeVisible();

  // The snapshot table headers.
  await expect(page.getByRole("columnheader", { name: "Accuracy" })).toBeVisible();
  await expect(
    page.getByRole("columnheader", { name: "Delta", exact: true }),
  ).toBeVisible();
});

test("the snapshot table shows a per-snapshot delta and per-class change", async ({
  page,
}) => {
  await page.goto("/eval");

  // The newest snapshot row carries a delta against the previous one (a signed
  // percentage-point value). At least one "pp" delta is present.
  await expect(page.getByText(/pp$/).first()).toBeVisible();

  // The per-class change section compares the latest two snapshots.
  await expect(
    page.getByRole("heading", { name: "Per-class change, latest snapshot" }),
  ).toBeVisible();
  await expect(
    page.getByRole("columnheader", { name: "Precision delta" }),
  ).toBeVisible();
  await expect(
    page.getByRole("columnheader", { name: "Recall delta" }),
  ).toBeVisible();
});
