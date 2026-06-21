import { test, expect } from "@playwright/test";

// These run against the local run bundles in ../runs (testpass2 etc. are present).

test("run list loads and shows runs with verdicts", async ({ page }) => {
  await page.goto("/runs");
  await expect(page.getByRole("heading", { name: /Runs/ })).toBeVisible();
  await expect(page.getByRole("link", { name: "testpass2" })).toBeVisible();
});

test("verdict filter dropdown opens without crashing", async ({ page }) => {
  // This is the regression guard for the Base UI menu errors (asChild,
  // MenuGroupContext) that tsc and next build did not catch.
  await page.goto("/runs");
  await page.getByRole("button", { name: /Verdict/ }).click();
  // The group label only renders if the menu opened correctly.
  await expect(page.getByText("Filter by verdict")).toBeVisible();
  const passOption = page.getByRole("menuitemradio", { name: "Pass" });
  await expect(passOption).toBeVisible();
  await passOption.click();
});

test("run detail shows the verdict and pipeline", async ({ page }) => {
  await page.goto("/runs/testpass2");
  await expect(page.getByRole("heading", { name: "testpass2" })).toBeVisible();
  await expect(page.getByText(/nf-core\/rnaseq/).first()).toBeVisible();
});

test("a missing run returns 404", async ({ page }) => {
  const res = await page.goto("/runs/does-not-exist");
  expect(res?.status()).toBe(404);
});

test("detector eval page loads", async ({ page }) => {
  await page.goto("/eval");
  await expect(page.getByRole("heading", { name: /Detector/ })).toBeVisible();
});
