import { test, expect } from "@playwright/test";

// Concordance QC labeling (cross-tool corroboration). The engine emits
// concordance checks (a result corroborated across independent tools) as QCResult
// entries carrying kind "concordance". The QC panel pulls these into their own
// "Concordance (cross-tool corroboration)" section, separate from the metric and
// structural checks. A concordance check with no second tool to compare against
// reports status "unverified", a neutral state rendered as a grey pill (not a
// failure).

test("concordance checks render in their own labeled section", async ({
  page,
}) => {
  await page.goto("/runs/concordance-fixture");

  // The QC tab is the default tab; the concordance section is labeled distinctly.
  await expect(
    page.getByText("Concordance (cross-tool corroboration)"),
  ).toBeVisible();

  // The passing cross-tool agreement check renders as a row in the concordance
  // table. Scope to a table cell so we assert the section lists it.
  await expect(
    page.getByRole("cell", { name: "gene_count_agreement:salmon_vs_featurecounts" }),
  ).toBeVisible();

  // The "unverified" concordance check (no second tool to compare against) renders
  // too, with the neutral Unverified status pill rather than a pass/warn/fail.
  await expect(
    page.getByRole("cell", { name: "variant_agreement:gatk_vs_deepvariant" }),
  ).toBeVisible();
  await expect(page.getByText("Unverified")).toBeVisible();

  // The metric check stays in the per-sample grouping, not the concordance section.
  await expect(page.getByText("Per-sample checks")).toBeVisible();
  await expect(
    page.getByRole("cell", { name: "alignment_rate:SAMPLE_A" }),
  ).toBeVisible();
});
