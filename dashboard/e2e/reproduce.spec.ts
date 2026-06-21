import { test, expect } from "@playwright/test";

// One-click reproduce. runs/reproduce-fixture has a launch.json manifest and a
// finished run_record.json, so its detail page shows the reproduce actions. We
// assert the actions render and that "Edit and relaunch" opens the launch form
// pre-filled from the manifest. We deliberately do NOT click "Reproduce exactly"
// here: that dispatches a real pipeline run.

const FIXTURE = "reproduce-fixture";

test("the run detail page offers reproduce actions", async ({ page }) => {
  await page.goto(`/runs/${FIXTURE}`);

  await expect(
    page.getByRole("heading", { name: FIXTURE }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Reproduce exactly" }),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: "Edit and relaunch" }),
  ).toBeVisible();
});

test("edit and relaunch opens the launch form pre-filled from the manifest", async ({
  page,
}) => {
  await page.goto(`/runs/${FIXTURE}`);

  await page.getByRole("link", { name: "Edit and relaunch" }).click();

  // We land on the new run form with from=<id> in the URL.
  await expect(page).toHaveURL(new RegExp(`/runs/new\\?from=${FIXTURE}`));
  await expect(page.getByRole("heading", { name: "New run" })).toBeVisible();

  // The manifest pre-fills the inputs: the sample sheet path and the genome key.
  await expect(page.getByText(/Pre-filled from reproduce-fixture/)).toBeVisible();
  await expect(page.getByLabel("Sample sheet path")).toHaveValue(
    /reproduce-fixture\/samplesheet\.csv$/,
  );
  await expect(page.getByLabel("iGenomes key")).toHaveValue("GRCh38");
});

test("a run without a manifest does not show reproduce actions", async ({
  page,
}) => {
  // testpass2 predates the manifest, so the reproduce actions are not offered.
  await page.goto("/runs/testpass2");

  await expect(page.getByRole("heading", { name: "testpass2" })).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Reproduce exactly" }),
  ).toHaveCount(0);
});
