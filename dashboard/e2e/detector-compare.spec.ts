import { test, expect } from "@playwright/test";

// Detector comparison (PRD contract A). /eval shows the latest snapshot per
// detector side by side, so rules vs llm is a direct comparison (overall accuracy
// plus per-class recall). The fixture eval history (e2e/fixtures/_eval_history)
// carries snapshots tagged "rules" and "llm", provisioned into the eval-history
// file by the global setup, so the compare view renders two columns.

test("the eval page shows a side-by-side detector comparison", async ({
  page,
}) => {
  await page.goto("/eval");

  await expect(
    page.getByRole("heading", { name: "Detector comparison" }),
  ).toBeVisible();
  await expect(
    page.getByText("Latest snapshot per detector"),
  ).toBeVisible();

  // Both detector columns from the fixture history are present as column headers.
  await expect(page.getByRole("columnheader", { name: "Rules", exact: true })).toBeVisible();
  await expect(page.getByRole("columnheader", { name: "LLM" })).toBeVisible();
});

test("the comparison shows overall accuracy and per-class recall rows", async ({
  page,
}) => {
  await page.goto("/eval");

  // Scope to the comparison section (other tables on the page also list classes),
  // labelled by its heading, so the assertions target the side-by-side view only.
  const compare = page.getByRole("region", { name: "Detector comparison" });

  // The headline accuracy row, the direct rules-vs-llm comparison.
  await expect(
    compare.getByRole("rowheader", { name: "Overall accuracy" }),
  ).toBeVisible();

  // A per-class row from the fixture (bad_param differs between the two detectors:
  // the older rules snapshot scored it lower, the llm one is perfect).
  await expect(
    compare.getByRole("rowheader", { name: "bad_param" }),
  ).toBeVisible();
});
