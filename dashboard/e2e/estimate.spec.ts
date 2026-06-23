import { test, expect } from "@playwright/test";

// Pre-run estimate on the launch form (PRD contract B). After a plan preview the
// form fetches `/api/runs/estimate` and shows the estimated runtime and cost
// before the user launches. We mock both the plan route (so a plan is previewed
// without fixture data on disk) and the estimate route (so the figures are
// deterministic and no real CLI runs), then assert the estimate renders.

test("the launch form shows a runtime and cost estimate after previewing a plan", async ({
  page,
}) => {
  // A deterministic plan so the preview succeeds and the estimate fetch fires.
  await page.route("**/api/runs/plan", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        plan: {
          assay: "rnaseq",
          pipeline: "nf-core/rnaseq",
          revision: "3.26.0",
          params: { genome: "GRCh38" },
          rationale: "RNA-seq differential expression.",
          warnings: [],
        },
      }),
    });
  });

  // A history-based estimate: 1 hour, 12.50 USD, derived from 3 prior runs.
  await page.route("**/api/runs/estimate", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        basis: "history",
        pipeline: "nf-core/rnaseq",
        n_samples: 4,
        n_prior_runs: 3,
        est_runtime_sec: 3600,
        est_peak_mem_mb: 8192,
        est_total_cpu_hours: 5.0,
        est_cost: 12.5,
        currency: "USD",
        rate_cpu_hour: 2.5,
        rate_mem_gb_hour: 0.0,
        note: "Scaled from per-sample averages.",
      }),
    });
  });

  await page.goto("/runs/new");

  await page.getByLabel("Goal").fill("RNA-seq differential expression");
  await page.getByLabel("Sample sheet path").fill("/data/samplesheet.csv");
  await page.getByLabel("iGenomes key").fill("GRCh38");
  await page.getByRole("button", { name: "Preview plan" }).click();

  // The estimate section appears with the mocked runtime and cost.
  await expect(
    page.getByRole("heading", { name: "Estimate before you launch" }),
  ).toBeVisible();
  await expect(page.getByText("1h 0m")).toBeVisible();
  await expect(page.getByText("12.50 USD")).toBeVisible();
  await expect(page.getByText(/Based on 3 past runs/)).toBeVisible();
});

test("a heuristic estimate is labeled as such", async ({ page }) => {
  await page.route("**/api/runs/plan", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        plan: {
          assay: "rnaseq",
          pipeline: "nf-core/rnaseq",
          revision: "3.26.0",
          params: {},
          rationale: "RNA-seq.",
          warnings: [],
        },
      }),
    });
  });

  await page.route("**/api/runs/estimate", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        basis: "heuristic",
        pipeline: "nf-core/rnaseq",
        n_samples: 2,
        n_prior_runs: 0,
        est_runtime_sec: 1800,
        est_peak_mem_mb: 4096,
        est_total_cpu_hours: 1.0,
        est_cost: 0.0,
        currency: "USD",
        rate_cpu_hour: 0.0,
        rate_mem_gb_hour: 0.0,
        note: "No prior runs; a rough per-sample heuristic was used.",
      }),
    });
  });

  await page.goto("/runs/new");
  await page.getByLabel("Goal").fill("RNA-seq");
  await page.getByLabel("Sample sheet path").fill("/data/samplesheet.csv");
  await page.getByLabel("iGenomes key").fill("GRCh38");
  await page.getByRole("button", { name: "Preview plan" }).click();

  await expect(page.getByText(/Heuristic estimate for 2 samples/)).toBeVisible();
  await expect(
    page.getByText("Cost is zero at the default rates (local compute is free)."),
  ).toBeVisible();
});
