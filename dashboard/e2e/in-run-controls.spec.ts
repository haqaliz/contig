import { test, expect } from "@playwright/test";

// In-run controls (PRD feature 1). A live run (status running, pid 1) offers a
// Cancel button; a cancelled run (status cancelled) shows the cancelled view with
// a Resume button. We mock the cancel/resume API responses with page.route so the
// client wiring is exercised without shelling out to the real `contig` CLI.

test("a live run offers a Cancel button on the in-progress view", async ({
  page,
}) => {
  // live-fixture reads as running (status.json pid 1 -> EPERM -> isLive true).
  await page.goto("/runs/live-fixture");

  await expect(page.getByText(/in progress/i)).toBeVisible();
  await expect(page.getByRole("button", { name: "Cancel run" })).toBeVisible();
});

test("clicking Cancel POSTs to the cancel route and refreshes", async ({
  page,
}) => {
  let cancelled = false;
  await page.route("**/api/runs/live-fixture/cancel", async (route) => {
    cancelled = true;
    await route.fulfill({
      status: 202,
      contentType: "application/json",
      body: JSON.stringify({ ok: true }),
    });
  });

  await page.goto("/runs/live-fixture");
  await page.getByRole("button", { name: "Cancel run" }).click();

  await expect.poll(() => cancelled).toBe(true);
});

test("a cancelled run shows the cancelled view with a Resume button", async ({
  page,
}) => {
  await page.goto("/runs/cancelled-fixture");

  await expect(page.getByText("This run was cancelled")).toBeVisible();
  await expect(page.getByRole("button", { name: "Resume run" })).toBeVisible();
});

test("clicking Resume POSTs to the resume route", async ({ page }) => {
  let resumed = false;
  await page.route("**/api/runs/cancelled-fixture/resume", async (route) => {
    resumed = true;
    await route.fulfill({
      status: 202,
      contentType: "application/json",
      body: JSON.stringify({ run_id: "cancelled-fixture" }),
    });
  });

  await page.goto("/runs/cancelled-fixture");
  await page.getByRole("button", { name: "Resume run" }).click();

  await expect.poll(() => resumed).toBe(true);
});
