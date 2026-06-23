import { test, expect } from "@playwright/test";

// Signed/verified badge (PRD contracts E, F). A run that carries a signature.json
// is checked by `contig verify <id> --json`, which adds `signed` and
// `signature_ok` to its report. The output-integrity card surfaces a badge: signed
// with signature_ok is "Signed, signature verified"; signed but not ok is a tamper
// warning. The badge rides on the verify report, so we mock that route (as the
// drift spec does) to exercise both branches deterministically, without needing the
// signing toolchain in the test environment.

test("a signed run with a valid signature shows the verified badge", async ({
  page,
}) => {
  await page.route("**/api/runs/signed-fixture/verify", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        ok: true,
        changed: [],
        missing: [],
        signed: true,
        signature_ok: true,
      }),
    });
  });

  await page.goto("/runs/signed-fixture");
  await page.getByRole("button", { name: /Verify outputs/ }).click();

  await expect(page.getByText("Signed, signature verified")).toBeVisible();
  await expect(
    page.getByText(/that signature verified against the recorded bundle/),
  ).toBeVisible();
});

test("a signed run whose signature does not verify shows a tamper warning", async ({
  page,
}) => {
  await page.route("**/api/runs/signed-fixture/verify", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        ok: true,
        changed: [],
        missing: [],
        signed: true,
        signature_ok: false,
      }),
    });
  });

  await page.goto("/runs/signed-fixture");
  await page.getByRole("button", { name: /Verify outputs/ }).click();

  await expect(page.getByText("Signature mismatch")).toBeVisible();
  await expect(
    page.getByText(/did not verify against the recorded bundle/),
  ).toBeVisible();
});
