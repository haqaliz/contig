import { test, expect } from "@playwright/test";

// Resources and cost card on the run detail page (PRD contracts A, B). Per-task
// duration and peak memory come straight from run_record.json resource_usage, so
// the table renders with no CLI. The total cost comes from `contig cost <id>
// --json`; we mock that API route so the card's wiring is tested regardless of
// whether the engine has wired the cost command in this environment.

test("the run detail page shows per-task duration and peak memory", async ({
  page,
}) => {
  // resource-fixture records two tasks with realtime, peak_rss, and %cpu.
  await page.goto("/runs/resource-fixture");

  await expect(page.getByText("Resources and cost")).toBeVisible();

  // Durations are formatted compactly: 123s -> "2m 3s", 2048s -> "34m 8s".
  await expect(page.getByText("2m 3s")).toBeVisible();
  await expect(page.getByText("34m 8s")).toBeVisible();
  // Memory crosses to GB once it passes 1024 MB: 512 MB stays MB, 4096 -> 4.0 GB.
  await expect(page.getByText("512 MB")).toBeVisible();
  await expect(page.getByText("4.0 GB")).toBeVisible();
  // Both task names appear in the table.
  await expect(page.getByText("FASTQC (SAMPLE_A)")).toBeVisible();
  await expect(page.getByText("SALMON_QUANT (SAMPLE_A)")).toBeVisible();
});

test("entering rates recomputes the total cost from the engine", async ({
  page,
}) => {
  // Mock the cost route so applying rates yields a known total, exercising the
  // recompute wiring without depending on the engine's cost command here.
  await page.route("**/api/runs/resource-fixture/cost**", async (route) => {
    const url = new URL(route.request().url());
    const cpu = url.searchParams.get("cpuHour");
    // The default (no rates) total is zero; with a cpu rate, return a real total.
    const total = cpu ? 0.5 : 0;
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        currency: "USD",
        rate_cpu_hour: cpu ? Number(cpu) : 0,
        rate_mem_gb_hour: 0,
        total,
        by_task: [],
      }),
    });
  });

  await page.goto("/runs/resource-fixture");

  await page.getByLabel("CPU rate (per core hour)").fill("0.05");
  await page.getByRole("button", { name: "Apply rates" }).click();

  // The header total updates to the mocked figure, formatted as currency.
  await expect(page.getByText("0.5000 USD")).toBeVisible();
});
