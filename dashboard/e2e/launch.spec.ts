import { test, expect } from "@playwright/test";

// The launch form renders the data -> plan -> approve -> launch fields, and the
// Launch button starts disabled (a launch is only allowed after a successful
// plan preview). We deliberately do NOT preview or launch here: a real plan
// needs fixture data on disk and a launch would spawn an actual pipeline run.

test("the new run form renders with launch disabled", async ({ page }) => {
  await page.goto("/runs/new");

  await expect(page.getByRole("heading", { name: "New run" })).toBeVisible();

  // The core fields are present and labeled.
  await expect(page.getByLabel("Goal")).toBeVisible();
  await expect(page.getByLabel("Sample sheet path")).toBeVisible();

  // Preview is available; Launch starts disabled until a plan is previewed.
  await expect(page.getByRole("button", { name: "Preview plan" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Launch run" })).toBeDisabled();
});

test("the runs list links to the new run form", async ({ page }) => {
  await page.goto("/runs");
  await expect(page.getByRole("link", { name: "New run" })).toBeVisible();
});
