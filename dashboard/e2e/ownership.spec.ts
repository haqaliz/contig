import { test, expect } from "@playwright/test";

// Per-user run isolation under the auth bypass (PRD contract E). With
// CONTIG_AUTH_DISABLED=1 (or no Auth0 env) the viewer is a synthetic local admin,
// so every run is visible, including runs with no owner.json (the fixtures are
// untagged). This pins the bypass behavior the rest of the suite depends on: local
// dev and the e2e suite see all runs, unchanged. The cross-user denial is covered
// by the unit-level ownership-filter test (e2e/ownership-filter.spec.ts), which
// exercises the pure filter for a non-admin viewer without needing a live tenant.

test("the admin (bypass) sees untagged runs in the list", async ({ page }) => {
  await page.goto("/runs");

  // The export-fixture has no owner.json, yet the admin bypass sees it.
  await expect(
    page.getByRole("link", { name: "export-fixture" }),
  ).toBeVisible();
});

test("the admin (bypass) can open an untagged run", async ({ page }) => {
  await page.goto("/runs/export-fixture");

  // The run detail renders (not a 404), so the admin can see an unowned run.
  await expect(
    page.getByRole("heading", { name: "export-fixture" }),
  ).toBeVisible();
  // CardTitle renders as a div, so match the export card by text.
  await expect(page.getByText("Export and cite")).toBeVisible();
});
