import { test, expect } from "@playwright/test";

// The repair surfaces must not overclaim. Two defects motivated these tests, both
// found by the qc-anomaly slice's pre-flight audit:
//
//   1. `wasRepaired` (lib/derive.ts) was `repair_history.length > 0`, so the runs
//      table's "Repaired" badge fired for ANY recorded step -- including a step
//      that applied no patch. A green run carrying the engine's one
//      `qc_verdict_flagged` step would claim a repair that never happened, and so
//      would a pre-existing `gave_up` step (patch null). The badge now means what
//      it says: a patch was applied.
//   2. OUTCOME_META (components/run/repair-timeline.tsx) mapped only three
//      outcomes and fell back to `OUTCOME_META.gave_up.className` for anything
//      else, so the new literal rendered a raw snake_case label dressed in
//      give-up styling -- defeating the reason a distinct literal exists.
//
// Assertion discipline: the user-visible text is the contract (exact:true, so the
// mangled "Qc Anomaly" auto-title-case does not satisfy "QC anomaly"). For the
// give-up distinctness we assert the NEGATIVE -- that the two badges' classes
// DIFFER -- rather than pinning an amber Tailwind string, which would test the
// stylesheet rather than the behaviour, and would go vacuous on any restyle.

/** The outcome badge in the repair timeline: the element carrying the styling. */
function outcomeBadge(page: import("@playwright/test").Page, label: string) {
  return page.locator("span.font-medium").filter({ hasText: label }).first();
}

/** Open a run's Self-heal tab and wait until `expectLabel`'s badge is really there.
 *  The run page is server-rendered, so the tab exists before React has hydrated
 *  and an early click is swallowed silently (reliably so on testpass2, whose 234
 *  events make for a heavy page). Retrying the click until the panel content
 *  appears is attribute-agnostic and beats guessing at a "selected" state hook. */
async function openSelfHealTab(
  page: import("@playwright/test").Page,
  id: string,
  expectLabel: string,
) {
  await page.goto(`/runs/${id}`);
  await expect(page.getByRole("heading", { name: id })).toBeVisible();
  const tab = page.getByRole("tab", { name: /Self-heal/ });
  await expect(async () => {
    await tab.click();
    await expect(outcomeBadge(page, expectLabel)).toBeVisible({ timeout: 1000 });
  }).toPass({ timeout: 20000 });
}

function runRow(page: import("@playwright/test").Page, id: string) {
  return page.getByRole("row").filter({ hasText: id });
}

test("a green QC-flagged run does not claim a repair", async ({ page }) => {
  // Nothing was patched: the engine only recorded that QC reduced to fail.
  await page.goto("/runs");
  const row = runRow(page, "qc-anomaly-fixture");
  await expect(row).toBeVisible();
  await expect(row.getByText("Repaired", { exact: true })).toHaveCount(0);
});

test("a give-up that patched nothing does not claim a repair", async ({ page }) => {
  // Pre-existing misstatement, fixed deliberately: testpass2 carries one
  // `gave_up` step with patch null. No patch was applied, so no repair happened.
  await page.goto("/runs");
  const row = runRow(page, "testpass2");
  await expect(row).toBeVisible();
  await expect(row.getByText("Repaired", { exact: true })).toHaveCount(0);
});

test("a run whose patch was applied still claims a repair", async ({ page }) => {
  // The positive control. Without it, a `wasRepaired` that always returned false
  // would satisfy both assertions above.
  await page.goto("/runs");
  const row = runRow(page, "qc-anomaly-patched-fixture");
  await expect(row).toBeVisible();
  await expect(row.getByText("Repaired", { exact: true })).toHaveCount(1);
});

test("the QC-verdict flag renders its own outcome and failure labels", async ({
  page,
}) => {
  await openSelfHealTab(page, "qc-anomaly-fixture", "QC verdict flagged");

  // Not the raw literal, and not the auto-title-cased "Qc Anomaly".
  await expect(page.getByText("QC verdict flagged", { exact: true })).toBeVisible();
  await expect(page.getByText("QC anomaly", { exact: true })).toBeVisible();
  await expect(page.getByText("qc_verdict_flagged", { exact: true })).toHaveCount(0);
  await expect(page.getByText("Qc Anomaly", { exact: true })).toHaveCount(0);

  // It recorded no patch, and says so rather than implying one.
  await expect(page.getByText("No automatic patch.")).toBeVisible();
});

test("the QC-verdict flag is not styled as a give-up", async ({ page }) => {
  // The exact defect: an unmapped outcome fell through to gave_up's className.
  // Comparing the two rendered badges keeps this honest under any restyle -- it
  // fails iff the two share styling, and can never pass vacuously.
  await openSelfHealTab(page, "testpass2", "Gave up");
  const gaveUp = await outcomeBadge(page, "Gave up").getAttribute("class");
  expect(gaveUp).not.toBeNull();

  await openSelfHealTab(page, "qc-anomaly-fixture", "QC verdict flagged");
  const flagged = await outcomeBadge(page, "QC verdict flagged").getAttribute("class");
  expect(flagged).not.toBeNull();

  expect(flagged).not.toEqual(gaveUp);
});

test("a real patch and a QC flag keep their own outcome labels side by side", async ({
  page,
}) => {
  await openSelfHealTab(page, "qc-anomaly-patched-fixture", "QC verdict flagged");

  await expect(page.getByText("Patched and retried", { exact: true })).toBeVisible();
  await expect(page.getByText("QC verdict flagged", { exact: true })).toBeVisible();

  const patched = await outcomeBadge(page, "Patched and retried").getAttribute("class");
  const flagged = await outcomeBadge(page, "QC verdict flagged").getAttribute("class");
  expect(flagged).not.toEqual(patched);
});
