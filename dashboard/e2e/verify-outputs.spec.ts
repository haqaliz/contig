import { test, expect } from "@playwright/test";

// Output integrity badge (PRD contract B). A finished run records a sha256 per
// output file; the run detail page lets a user re-hash those files and shows a
// badge: "Outputs verified" (ok), "Drift detected" (changed/missing), or "Not
// captured" (the run recorded no output checksums). Verify POSTs to
// /api/runs/[id]/verify, which shells `contig verify <id> --json` and returns
// {ok, changed, missing}. The drift cases mock that route so the wiring is tested
// without manufacturing on-disk drift.

test("a run with no recorded outputs shows the not-captured badge", async ({
  page,
}) => {
  // scrnaseq-fixture is a finished run whose record carries no output checksums.
  await page.goto("/runs/scrnaseq-fixture");

  await expect(page.getByText("Not captured")).toBeVisible();
  // With nothing to verify, the verify button is not offered.
  await expect(
    page.getByRole("button", { name: /Verify outputs/ }),
  ).toHaveCount(0);
});

test("verifying a run with intact outputs shows the verified badge", async ({
  page,
}) => {
  // verify-fixture records one output whose file is present on disk, so the real
  // `contig verify` reports ok. Before a verify the badge invites the check.
  await page.goto("/runs/verify-fixture");
  await expect(page.getByText("Not yet verified")).toBeVisible();

  await page.getByRole("button", { name: /Verify outputs/ }).click();

  await expect(page.getByText("Outputs verified")).toBeVisible();
});

test("a drifted run shows the drift badge with the changed and missing files", async ({
  page,
}) => {
  // Mock the verify route so it reports drift, exercising the drift rendering
  // without manufacturing real on-disk drift.
  await page.route("**/api/runs/verify-fixture/verify", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        ok: false,
        changed: ["multiqc_report.html"],
        missing: ["star_salmon/SAMPLE_A.bam"],
      }),
    });
  });

  await page.goto("/runs/verify-fixture");
  await page.getByRole("button", { name: /Verify outputs/ }).click();

  await expect(page.getByText("Drift detected")).toBeVisible();
  await expect(page.getByText("multiqc_report.html")).toBeVisible();
  await expect(page.getByText("star_salmon/SAMPLE_A.bam")).toBeVisible();
});
