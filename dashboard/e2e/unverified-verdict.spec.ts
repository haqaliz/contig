import { test, expect } from "@playwright/test";

// The dashboard's overallQc (lib/derive.ts) is a SECOND, divergent copy of the
// engine's verdict reducer (overall_verdict in src/contig/models.py). The
// engine's reducer has a real "unverified" arm and excludes "informational"
// checks from the severity decision; overallQc had neither, so a run whose
// qc_results are all "unverified" (or all informational + unverified) landed on
// "pass" and explainVerdict rendered the false claim "PASS: all N checks
// passed" right next to a badge that (correctly) reads "Unverified". These two
// fixtures prove both arms: unverified-fixture proves the missing "unverified"
// arm; informational-only-fixture additionally proves the informational skip
// (its one severity-bearing-looking result is marked informational, so it must
// not manufacture a pass).

test("an all-unverified run does not claim a pass", async ({ page }) => {
  await page.goto("/runs/unverified-fixture");

  await expect(
    page.getByRole("heading", { name: "unverified-fixture" }),
  ).toBeVisible();

  // The verdict badge reads Unverified (the stored, engine-computed verdict).
  await expect(page.getByText("Unverified").first()).toBeVisible();

  // The reason must never claim a pass.
  await expect(page.getByText(/PASS: all \d+ checks? passed/)).toHaveCount(0);

  // "Decided by" states nothing decided this run, not a fail/warn tally either.
  await expect(page.getByText("Decided by")).toBeVisible();
  await expect(page.getByText(/no check could corroborate this run/i)).toBeVisible();
});

test("an informational-only run does not claim a pass", async ({ page }) => {
  await page.goto("/runs/informational-only-fixture");

  await expect(
    page.getByRole("heading", { name: "informational-only-fixture" }),
  ).toBeVisible();

  await expect(page.getByText("Unverified").first()).toBeVisible();

  // The one severity-bearing-looking check is marked informational and must not
  // be enough to manufacture a pass.
  await expect(page.getByText(/PASS: all \d+ checks? passed/)).toHaveCount(0);

  await expect(page.getByText("Decided by")).toBeVisible();
  await expect(page.getByText(/no check could corroborate this run/i)).toBeVisible();
});
