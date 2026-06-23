import { test, expect } from "@playwright/test";

// Corpus coverage panel and clusters view on /eval (PRD contracts B, C). Both fetch
// their read-only routes on mount; we mock the routes so the views render
// deterministically without the engine's coverage/clusters CLI.

test("the coverage panel shows per-class support and flags thin coverage", async ({
  page,
}) => {
  await page.route("**/api/eval/coverage", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        total: 11,
        per_class: { oom: 5, missing_reference: 4, bad_param: 2 },
        thin: ["bad_param"],
        by_source: { corpus: 8, pending: 3 },
        confirmed_over_time: [
          { timestamp: "2026-06-01T00:00:00Z", confirmed: 6 },
          { timestamp: "2026-06-20T00:00:00Z", confirmed: 11 },
        ],
      }),
    });
  });
  // Stub the clusters route too so the page settles (both load on the eval page).
  await page.route("**/api/eval/clusters", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([]),
    });
  });

  await page.goto("/eval");

  const panel = page.getByTestId("coverage-panel");
  await expect(panel.getByText("Per-class support")).toBeVisible();
  await expect(panel.getByText("11 cases")).toBeVisible();

  // Each class is listed; the thin class is flagged in the thin-coverage row.
  await expect(panel.getByText("oom")).toBeVisible();
  await expect(panel.getByText("missing_reference")).toBeVisible();
  await expect(panel.getByText("Thin coverage")).toBeVisible();
  await expect(panel.getByText("fewer than 3 cases")).toBeVisible();

  // The by-source breakdown.
  await expect(panel.getByText("By source")).toBeVisible();
  await expect(panel.getByText("corpus", { exact: true })).toBeVisible();
});

test("the clusters view lists the recurring failure modes worst first", async ({
  page,
}) => {
  await page.route("**/api/eval/coverage", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        total: 0,
        per_class: {},
        thin: [],
        by_source: {},
      }),
    });
  });
  await page.route("**/api/eval/clusters", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([
        {
          failure_class: "oom",
          signature: "sig-oom-137",
          count: 4,
          case_ids: ["case-a", "case-b", "case-c", "case-d"],
        },
        {
          failure_class: "missing_reference",
          signature: "sig-missing-ref",
          count: 2,
          case_ids: ["case-e", "case-f"],
        },
      ]),
    });
  });

  await page.goto("/eval");

  const view = page.getByTestId("clusters-view");
  await expect(view.getByText("Failure clusters, worst first")).toBeVisible();

  // Both clusters render with their friendly class label and counts.
  await expect(view.getByText("Out of memory")).toBeVisible();
  await expect(view.getByText("4 cases")).toBeVisible();
  await expect(view.getByText("Missing reference")).toBeVisible();
  await expect(view.getByText("2 cases")).toBeVisible();

  // The case ids of the worst cluster are listed.
  await expect(view.getByText("case-a")).toBeVisible();
  await expect(view.getByText("sig-oom-137")).toBeVisible();
});
