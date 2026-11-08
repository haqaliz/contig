import { expect, test } from "@playwright/test";

test("research page renders the read-only workbench tables", async ({ page }) => {
  await page.goto("/research");
  await expect(page.getByRole("heading", { name: "Research", level: 1 })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Variant evidence" })).toBeVisible();
  await expect(page.getByText("BRCA1").first()).toBeVisible();
  await expect(page.getByRole("heading", { name: "Coverage readiness" })).toBeVisible();
  await expect(page.getByText("GENE3").first()).toBeVisible();
  await expect(page.getByRole("heading", { name: "Ask the run" })).toBeVisible();
});
