import { test, expect } from "@playwright/test";

// Cross-run benchmark section on the run page (PRD contract A). The card fetches
// /api/runs/[id]/benchmark on mount and renders run vs reference per metric. We mock
// the benchmark route so the section renders deterministically without the engine's
// benchmark CLI: one spec for a drift report, one for the no_reference state.

test("the benchmark section shows run vs reference per metric and flags drift", async ({
  page,
}) => {
  await page.route(
    "**/api/runs/benchmark-fixture/benchmark*",
    async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          reference_run_id: "reference-run-001",
          tolerance: 0.1,
          matched: 1,
          drifted: 1,
          checks: [
            {
              name: "min_sample_count",
              run_value: 2,
              reference_value: 2,
              within_tolerance: true,
              delta: 0,
            },
            {
              name: "median_pct_reads_mapped",
              run_value: 71.2,
              reference_value: 92.4,
              within_tolerance: false,
              delta: -21.2,
            },
          ],
          status: "drift",
        }),
      });
    },
  );

  await page.goto("/runs/benchmark-fixture");

  const card = page.getByTestId("benchmark-card");
  // The drift badge and the reference run id.
  await expect(card.getByText("Drift detected")).toBeVisible();
  await expect(card.getByText("reference-run-001")).toBeVisible();

  // The per-metric comparison: both metric names, with the drifted one flagged.
  await expect(card.getByText("median_pct_reads_mapped")).toBeVisible();
  await expect(card.getByText("min_sample_count")).toBeVisible();
  // The drifted metric reads as "drift", the matched one as "within".
  await expect(card.getByText("drift", { exact: true })).toBeVisible();
  await expect(card.getByText("within", { exact: true })).toBeVisible();
});

test("the benchmark section degrades to a no-reference state", async ({
  page,
}) => {
  await page.route(
    "**/api/runs/benchmark-fixture/benchmark*",
    async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          reference_run_id: null,
          tolerance: 0.1,
          matched: 0,
          drifted: 0,
          checks: [],
          status: "no_reference",
        }),
      });
    },
  );

  await page.goto("/runs/benchmark-fixture");

  const card = page.getByTestId("benchmark-card");
  await expect(card.getByText("No reference", { exact: true })).toBeVisible();
  await expect(
    card.getByText(/No reference run is set for this pipeline and assay/),
  ).toBeVisible();
});
