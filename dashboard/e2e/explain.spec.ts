import { test, expect } from "@playwright/test";

// "Why this verdict": the verdict card gains a "Decided by" section that lists
// the deciding checks (value vs expected_range) and a one-line reason. The
// reason mirrors src/contig/models.py exactly (explainVerdict in lib/derive.ts).
// runs/warn-fixture is a warn run: two salmon_mapping_rate checks warn (58.1 and
// 59.4 vs >= 60.0), the rest pass, so the verdict is warn and the lowest
// deciding check is salmon_mapping_rate:SAMPLE_A at 58.1.

test("the verdict card explains a warn verdict with its deciding checks", async ({
  page,
}) => {
  await page.goto("/runs/warn-fixture");

  await expect(page.getByRole("heading", { name: "warn-fixture" })).toBeVisible();

  // The "Decided by" section is present with the one-line reason.
  await expect(page.getByText("Decided by")).toBeVisible();
  await expect(
    page.getByText(
      /WARN: 2 of 4 checks flagged \(lowest: salmon_mapping_rate:SAMPLE_A 58\.1 vs >= 60\.0\)/,
    ),
  ).toBeVisible();

  // Both warn checks are listed as deciding, with value vs expected range.
  await expect(
    page.getByText("salmon_mapping_rate:SAMPLE_A").first(),
  ).toBeVisible();
  await expect(page.getByText("58.1 vs >= 60.0").first()).toBeVisible();
});

test("a passing run explains that every check passed", async ({ page }) => {
  await page.goto("/runs/testpass2");

  await expect(page.getByText("Decided by")).toBeVisible();
  // testpass2 passes with 160 checks: the reason reports all passed.
  await expect(page.getByText(/PASS: all 160 checks passed/)).toBeVisible();
});

test("a task-failed run explains that the run did not complete", async ({
  page,
}) => {
  // taskfail-fixture has one FAILED event (exit 137): the task path wins, so the
  // reason is the "did not complete" message, ahead of any QC consideration.
  await page.goto("/runs/taskfail-fixture");

  await expect(page.getByText("Decided by")).toBeVisible();
  await expect(
    page.getByText(/Run did not complete: 1 task failed/),
  ).toBeVisible();
});

test("a QC-failed run explains which check flagged it", async ({ page }) => {
  // variant-bad completes its task but a QC check fails (ts_tv_ratio:S1 3.5 vs
  // [1.8, 2.4]): the QC path decides, naming the flagged check.
  await page.goto("/runs/variant-bad");

  await expect(page.getByText("Decided by")).toBeVisible();
  await expect(
    page.getByText(
      /FAIL: 1 of 3 checks flagged \(lowest: ts_tv_ratio:S1 3\.5 vs \[1\.8, 2\.4\]\)/,
    ),
  ).toBeVisible();
});
