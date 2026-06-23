import { test, expect } from "@playwright/test";

// Structural QC labeling (PRD contracts C, F). The engine emits structural and
// integrity checks (expected outputs present, non-empty, valid) as QCResult
// entries carrying kind "structural". The QC panel pulls these into their own
// "Structural and integrity checks" section, separate from the metric checks, so a
// reviewer can tell a content-metric failure from a missing-output failure.

test("structural checks render in their own labeled section", async ({
  page,
}) => {
  await page.goto("/runs/structural-fixture");

  // The QC tab is the default tab; the structural section is labeled distinctly.
  await expect(
    page.getByText("Structural and integrity checks"),
  ).toBeVisible();

  // The failing structural check (a missing required output) renders as a row in
  // the QC table (the same key also appears in the verdict summary, so scope to a
  // table cell to assert the structural section lists it).
  await expect(
    page.getByRole("cell", { name: "output_present:multiqc_report.html" }),
  ).toBeVisible();

  // The metric check stays in the per-sample grouping, not the structural section.
  await expect(page.getByText("Per-sample checks")).toBeVisible();
  await expect(
    page.getByRole("cell", { name: "alignment_rate:SAMPLE_A" }),
  ).toBeVisible();
});
