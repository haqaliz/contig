import { expect, test } from "@playwright/test";

// Run with CONTIG_E2E_DISCOVERY=1. The default research spec uses the explicit
// CONTIG_RESEARCH_DIR manifest; this one exercises the per-run fallback.
test.skip(!process.env.CONTIG_E2E_DISCOVERY, "set CONTIG_E2E_DISCOVERY=1");

test("research auto-discovers the newest per-run manifest", async ({ page }) => {
  await page.goto("/research");
  await expect(page.getByText("Auto-discovered from")).toBeVisible();
  await expect(page.getByText("runs/r1/research")).toBeVisible();
  await expect(page.getByText("BRCA1").first()).toBeVisible();
  await expect(page.getByRole("heading", { name: "Coverage readiness" })).toBeVisible();
});
