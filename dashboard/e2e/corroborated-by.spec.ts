import { test, expect } from "@playwright/test";

// The "Corroborated by ..." line in the concordance card (C7 M5). This mirrors
// the Python helper src/contig/verification/annotation_surface.py: it READS M4's
// already-computed consequence_concordance / gene_symbol_concordance QC results
// plus the run's annotation_identity and renders one plain-language line, never
// recomputing. The line is shown ONLY when consequence_concordance carries a
// value (PRD D2): a single-annotator / value-null record omits it entirely.

test("dual-annotated run renders the corroborated-by line + cache/build", async ({
  page,
}) => {
  await page.goto("/runs/corroboration-fixture");

  // The concordance card is present (QC is the default tab).
  await expect(
    page.getByText("Concordance (cross-tool corroboration)"),
  ).toBeVisible();

  // Annotator names come from annotation_identity; the counts/fractions are read
  // from the concordance messages/values (never recomputed).
  await expect(
    page.getByText(
      "Corroborated by VEP and SnpEff: 48/50 consequences agree (0.96)",
    ),
  ).toBeVisible();
  // The gene-symbol clause is marked informational so a low fraction never reads
  // as a failure (PRD D3 / S-1).
  await expect(
    page.getByText("gene symbols 46/50 (0.92, informational)"),
  ).toBeVisible();

  // The annotation cache/build id is surfaced, labeled "cache/build" (never
  // "database version" -- PRD D1).
  await expect(page.getByText("cache/build 110_GRCh38")).toBeVisible();
});

test("single-annotator (value-null) run omits the corroborated-by line", async ({
  page,
}) => {
  await page.goto("/runs/corroboration-absent-fixture");

  // The concordance card still renders the unverified check row...
  await expect(
    page.getByText("Concordance (cross-tool corroboration)"),
  ).toBeVisible();
  await expect(
    page.getByRole("cell", { name: "consequence_concordance" }),
  ).toBeVisible();

  // ...but no corroborated-by line is rendered (consequence value is null, D2).
  await expect(page.getByText("Corroborated by")).toHaveCount(0);
});
