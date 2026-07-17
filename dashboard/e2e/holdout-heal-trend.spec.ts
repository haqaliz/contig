import { test, expect } from "@playwright/test";

// Holdout-accuracy + self-heal outcome-match trends (C6 self-heal regression
// guard). /eval shows a held-out-accuracy-over-time trend and a self-heal
// outcome-match-over-time trend, mirroring the shipped detector EvalHistory:
// an inline SVG sparkline plus a snapshot table with per-snapshot deltas. The
// fixtures _holdout_history/holdout_history.jsonl and
// _heal_history/heal_history.jsonl each carry 2 snapshots, so both trends and
// their delta indicators render. We assert structure and a delta, not exact
// percentages, so the test stays valid if the engine appends more snapshots.

test("the eval page renders the held-out-accuracy-over-time trend", async ({
  page,
}) => {
  await page.goto("/eval");

  await expect(
    page.getByRole("heading", { name: "Held-out accuracy over time" }),
  ).toBeVisible();
  await expect(
    page.getByRole("img", { name: "Held-out detector accuracy over time" }),
  ).toBeVisible();

  // At least one signed percentage-point delta renders in the page (the
  // detector trend above may also show one; this asserts the series exists,
  // not that it is uniquely attributable, matching eval-history.spec.ts).
  await expect(page.getByText(/pp$/).first()).toBeVisible();
});

test("the eval page renders the self-heal-outcome-match-over-time trend", async ({
  page,
}) => {
  await page.goto("/eval");

  await expect(
    page.getByRole("heading", { name: "Self-heal outcome-match over time" }),
  ).toBeVisible();
  await expect(
    page.getByRole("img", { name: "Self-heal outcome-match over time" }),
  ).toBeVisible();
  await expect(
    page.getByRole("columnheader", { name: "Recovery" }),
  ).toBeVisible();

  // At least one signed percentage-point delta renders in the page.
  await expect(page.getByText(/pp$/).first()).toBeVisible();
});
