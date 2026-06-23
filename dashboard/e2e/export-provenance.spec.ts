import { test, expect } from "@playwright/test";

// Provenance export buttons on the run page (PRD contract C). A finished run can
// be downloaded as an RO-Crate metadata JSON and as a citation-ready methods
// paragraph, via read-only routes that shell `contig export --rocrate` and
// `contig methods`. We assert the buttons render and point at the right routes;
// the bytes those routes return are produced by the engine (covered cross-layer),
// so we pin the dashboard contract here: the links and their targets.

test("the run page offers RO-Crate and methods downloads", async ({ page }) => {
  await page.goto("/runs/export-fixture");

  // CardTitle renders as a div, not a heading, so match by text.
  await expect(page.getByText("Export and cite")).toBeVisible();

  const crate = page.getByRole("link", { name: "Download RO-Crate" });
  const methods = page.getByRole("link", { name: "Download methods" });
  await expect(crate).toBeVisible();
  await expect(methods).toBeVisible();

  // The links target the read-only export and methods routes for this run.
  await expect(crate).toHaveAttribute("href", "/api/runs/export-fixture/export");
  await expect(methods).toHaveAttribute(
    "href",
    "/api/runs/export-fixture/methods",
  );
  // They are real download anchors, not navigations.
  await expect(crate).toHaveAttribute("download", "");
});
