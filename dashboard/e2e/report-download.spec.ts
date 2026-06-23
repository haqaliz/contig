import { test, expect } from "@playwright/test";

// Shareable report download (PRD contracts D, F). A finished run can be downloaded
// as a self-contained HTML report (the print-to-PDF-friendly page) via a read-only
// route that shells `contig show <id> --html`. We assert the button renders and
// points at the report route; the HTML the route returns is rendered by the engine
// (covered cross-layer), so we pin the dashboard contract here: the link and its
// target.

test("the run page offers a report download", async ({ page }) => {
  await page.goto("/runs/export-fixture");

  const report = page.getByRole("link", { name: "Download report" });
  await expect(report).toBeVisible();

  // The link targets the read-only report route for this run, and is a real
  // download anchor rather than a navigation.
  await expect(report).toHaveAttribute(
    "href",
    "/api/runs/export-fixture/report",
  );
  await expect(report).toHaveAttribute("download", "");
});
