import { test, expect } from "@playwright/test";

// The third-party `contig reproduce` listing surface (/reproduce, C8). Three
// fixtures are provisioned by global-setup:
//   reproduce-mixed  - every claim status literal (reproduced, within_tolerance,
//                      diverged, unverified) plus one UNKNOWN literal
//                      ("suspicious", the forward-compat probe), a repair
//                      history entry, and a signature sidecar.
//   reproduce-unverified - a non-zero exit (2): the whole run reads
//                      "Did not complete (exit 2)", never a claim-status badge.
//   reproduce-empty   - zero claims: the derived overall is an honest
//                      "Unverified" non-result.
// Reproduce bundles carry reproduce_record.json (NOT run_record.json), so they
// must be invisible to the first-party /runs list.

const IDS = ["reproduce-mixed", "reproduce-unverified", "reproduce-empty"];

// The tbody row whose id link matches the given id.
function rowFor(page: import("@playwright/test").Page, id: string) {
  return page
    .locator("tbody tr")
    .filter({ has: page.getByRole("link", { name: id, exact: true }) });
}

test("the header nav offers Reproduce and lands on /reproduce", async ({
  page,
}) => {
  await page.goto("/runs");
  const nav = page.getByRole("navigation", { name: "Primary" });
  await expect(nav.getByRole("link", { name: "Reproduce" })).toBeVisible();
  await nav.getByRole("link", { name: "Reproduce" }).click();
  await expect(page).toHaveURL(/\/reproduce$/);
  await expect(
    page.getByRole("heading", { name: /Reproductions/ }),
  ).toBeVisible();
});

test("the /reproduce listing shows all three fixtures with overall badges", async ({
  page,
}) => {
  await page.goto("/reproduce");

  for (const id of IDS) {
    await expect(page.getByRole("link", { name: id, exact: true })).toBeVisible();
  }

  // reproduce-mixed: worst-of over the claim statuses -> diverged.
  const mixed = rowFor(page, "reproduce-mixed");
  await expect(mixed.getByText("Diverged", { exact: true })).toBeVisible();

  // reproduce-unverified: non-zero exit -> its own "Did not complete" badge,
  // NEVER a claim-status badge (no exact "Unverified" pill in the row).
  const unverified = rowFor(page, "reproduce-unverified");
  await expect(
    unverified.getByText("Did not complete (exit 2)", { exact: true }),
  ).toBeVisible();
  await expect(unverified.getByText("Unverified", { exact: true })).toHaveCount(0);

  // reproduce-empty: zero claims -> honest "Unverified" non-result.
  const empty = rowFor(page, "reproduce-empty");
  await expect(empty.getByText("Unverified", { exact: true })).toBeVisible();
});

test("claim counts render per row, including unknown literals", async ({
  page,
}) => {
  await page.goto("/reproduce");

  // The mixed bundle has one claim per status; the unknown "suspicious"
  // literal is counted under its own key, not dropped or mislabeled.
  await expect(rowFor(page, "reproduce-mixed")).toContainText(
    "1 reproduced · 1 within tolerance · 1 diverged · 1 unverified · 1 suspicious",
  );
  await expect(rowFor(page, "reproduce-unverified")).toContainText(
    "1 unverified",
  );
  await expect(rowFor(page, "reproduce-empty")).toContainText("No claims");
});

test("clicking a reproduce id navigates to its detail URL", async ({ page }) => {
  await page.goto("/reproduce");
  await page.getByRole("link", { name: "reproduce-mixed", exact: true }).click();
  await expect(page).toHaveURL(/\/reproduce\/reproduce-mixed$/);
});

test("the page carries the honest CLI-guidance note", async ({ page }) => {
  await page.goto("/reproduce");
  await expect(
    page.getByRole("heading", { name: "How to reproduce a published paper" }),
  ).toBeVisible();
  await expect(page.getByText(/contig reproduce/)).toBeVisible();
});

test("/runs never lists the reproduce bundles", async ({ page }) => {
  await page.goto("/runs");
  for (const id of IDS) {
    await expect(page.getByRole("link", { name: id, exact: true })).toHaveCount(0);
  }
});