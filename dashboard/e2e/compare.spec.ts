import { test, expect } from "@playwright/test";

// These run against the local run bundles in ../runs. testpass2 (nf-core/rnaseq,
// pass) and variant-bad (nf-core/sarek, fail) differ a lot, so the diff view has
// plenty of differing fields to assert on.

test("compare view shows both run ids and a differing field", async ({ page }) => {
  await page.goto("/runs/compare?a=testpass2&b=variant-bad");

  await expect(page.getByRole("heading", { name: "Compare runs" })).toBeVisible();

  // Both run ids appear (in the intro line and as column headers).
  await expect(page.getByText("testpass2").first()).toBeVisible();
  await expect(page.getByText("variant-bad").first()).toBeVisible();

  // The two runs do not reproduce: the summary calls that out, and at least one
  // row is marked Changed (the verdicts: pass vs fail, and the pipelines differ).
  await expect(page.getByText("Did not reproduce")).toBeVisible();
  await expect(page.getByText("Changed").first()).toBeVisible();

  // The differing verdicts are both rendered as status badges.
  await expect(page.getByText("Pass").first()).toBeVisible();
  await expect(page.getByText("Fail").first()).toBeVisible();
});

test("compare view shows the picker when no params are given", async ({ page }) => {
  await page.goto("/runs/compare");

  await expect(page.getByRole("heading", { name: "Compare runs" })).toBeVisible();
  await expect(page.getByText("Choose two runs")).toBeVisible();

  // Labeled selects plus the Compare button make up the picker.
  await expect(page.getByLabel("Run A (baseline)")).toBeVisible();
  await expect(page.getByLabel("Run B (comparison)")).toBeVisible();
  await expect(page.getByRole("button", { name: "Compare" })).toBeVisible();
});

test("compare view keeps the picker visible alongside the results", async ({ page }) => {
  await page.goto("/runs/compare?a=testpass2&b=variant-bad");

  // The comparison renders...
  await expect(page.getByText("Did not reproduce")).toBeVisible();
  // ...and the picker is still on screen so either run can be swapped in place.
  await expect(page.getByText("Choose two runs")).toBeVisible();
  await expect(page.getByLabel("Run A (baseline)")).toBeVisible();
  await expect(page.getByLabel("Run B (comparison)")).toBeVisible();
});

test("the run chosen on one side is removed from the other side's options", async ({
  page,
}) => {
  await page.goto("/runs/compare?a=testpass2&b=variant-bad");

  // Open Run B's select; the id already chosen for A must not be offered.
  await page.getByLabel("Run B (comparison)").click();
  const listbox = page.getByRole("listbox");
  await expect(listbox).toBeVisible();
  await expect(listbox.getByRole("option", { name: "variant-bad" })).toBeVisible();
  await expect(listbox.getByRole("option", { name: "testpass2" })).toHaveCount(0);
});
