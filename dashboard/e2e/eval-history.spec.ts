import { test, expect, type Page } from "@playwright/test";

// Eval-history trend (PRD feature 3). /eval shows an accuracy-over-time trend
// (inline SVG, no chart dependency) plus a snapshot table with per-class deltas.
// The fixture src/contig/data/eval_history.jsonl carries 3 snapshots, so the
// trend and the delta indicators render. We assert structure and a delta, not
// exact percentages, so the test stays valid if the engine appends more snapshots.
//
// The /eval page also renders the holdout-accuracy and self-heal trends (C6),
// which mirror this component's column vocabulary (Accuracy, Delta, Precision
// delta, Recall delta, ...). Every query here is scoped to this trend's own
// <section aria-labelledby="trend-heading"> (exposed as an accessible region
// named "Accuracy over time") so it keeps asserting only against the detector
// trend, not the other sections sharing the same column names.
function detectorTrend(page: Page) {
  return page.getByRole("region", { name: "Accuracy over time", exact: true });
}

test("the eval page renders the accuracy-over-time trend", async ({ page }) => {
  await page.goto("/eval");
  const trend = detectorTrend(page);

  // The trend section and its inline SVG (labeled for screen readers).
  await expect(
    trend.getByRole("heading", { name: "Accuracy over time" }),
  ).toBeVisible();
  await expect(
    trend.getByRole("img", { name: "Detector accuracy over time" }),
  ).toBeVisible();

  // The snapshot table headers.
  await expect(trend.getByRole("columnheader", { name: "Accuracy" })).toBeVisible();
  await expect(
    trend.getByRole("columnheader", { name: "Delta", exact: true }),
  ).toBeVisible();
});

test("the snapshot table shows a per-snapshot delta and per-class change", async ({
  page,
}) => {
  await page.goto("/eval");
  const trend = detectorTrend(page);

  // The newest snapshot row carries a delta against the previous one (a signed
  // percentage-point value). At least one "pp" delta is present.
  await expect(trend.getByText(/pp$/).first()).toBeVisible();

  // The per-class change section compares the latest two snapshots.
  await expect(
    trend.getByRole("heading", { name: "Per-class change, latest snapshot" }),
  ).toBeVisible();
  await expect(
    trend.getByRole("columnheader", { name: "Precision delta" }),
  ).toBeVisible();
  await expect(
    trend.getByRole("columnheader", { name: "Recall delta" }),
  ).toBeVisible();
});
