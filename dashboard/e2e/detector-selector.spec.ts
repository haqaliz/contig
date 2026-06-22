import { test, expect } from "@playwright/test";

// Detector selector on /eval (PRD contract C). The failure detector is pluggable:
// the engine registers several behind one interface, and eval-detector scores any
// of them. The select drives ?detector=<name>, and the server page re-fetches the
// chosen detector's report. "rules" is the default. These assertions hold whether
// or not the engine has wired `eval-detector --detector` yet: the selector renders
// in both the live-report and the not-available branches, and the URL it drives is
// the contract. The report content for a given detector is covered by the engine
// suite, not here.

test("the eval page shows a detector selector defaulting to rules", async ({
  page,
}) => {
  await page.goto("/eval");

  const trigger = page.getByRole("combobox", { name: "Detector" });
  await expect(trigger).toBeVisible();
  // The default selection is the rules detector.
  await expect(trigger).toContainText("Rules (default)");
});

test("choosing a detector drives the ?detector query", async ({ page }) => {
  await page.goto("/eval");

  await page.getByRole("combobox", { name: "Detector" }).click();
  await page.getByRole("option", { name: "Rules, strict" }).click();

  // The selector navigates to ?detector=rules-strict so the server re-scores that
  // detector. Switching back to the default returns to a clean /eval url.
  await expect(page).toHaveURL(/\/eval\?detector=rules-strict$/);
  await expect(
    page.getByRole("combobox", { name: "Detector" }),
  ).toContainText("Rules, strict");

  await page.getByRole("combobox", { name: "Detector" }).click();
  await page.getByRole("option", { name: "Rules (default)" }).click();
  await expect(page).toHaveURL(/\/eval$/);
});
