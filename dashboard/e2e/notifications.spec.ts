import { test, expect } from "@playwright/test";

// Notifications feed (PRD contract A). The engine appends one JSON line per run
// lifecycle event to <runsDir>/notifications.jsonl: {ts, run_id, kind, message}
// with kind one of finished | failed | cancelled | awaiting_approval. The header
// bell reads them (newest first) into an activity panel; an awaiting_approval
// event links to its run. The _notifications fixture carries one of each kind, so
// the panel renders, the bell shows the awaiting dot, and the approval link works.

test("the header bell opens an activity panel listing recent events", async ({
  page,
}) => {
  await page.goto("/runs");

  // An awaiting_approval event is present, so the bell advertises it.
  const bell = page.getByRole("button", {
    name: /Recent activity, a run is awaiting approval/,
  });
  await expect(bell).toBeVisible();
  await bell.click();

  // The panel header and the four event kinds the fixture carries (scoped to the
  // list so the kind labels never collide with page chrome).
  await expect(page.getByText("Recent activity").first()).toBeVisible();
  const list = page.getByTestId("notification-list");
  await expect(list).toBeVisible();
  await expect(list.getByText("Finished", { exact: true })).toBeVisible();
  await expect(list.getByText("Failed", { exact: true })).toBeVisible();
  await expect(list.getByText("Cancelled", { exact: true })).toBeVisible();
  await expect(
    list.getByText("Awaiting approval", { exact: true }),
  ).toBeVisible();
});

test("newest events come first in the activity panel", async ({ page }) => {
  await page.goto("/runs");
  await page
    .getByRole("button", { name: /Recent activity/ })
    .click();

  // Read the rendered run ids in order; the fixture's latest event references
  // awaiting-approval-fixture and its oldest references scrnaseq-fixture.
  const runIds = await page
    .getByTestId("notification-list")
    .getByText(/-fixture$/)
    .allTextContents();
  expect(runIds[0]).toContain("awaiting-approval-fixture");
  expect(runIds[runIds.length - 1]).toContain("scrnaseq-fixture");
});

test("an awaiting_approval event links to its run", async ({ page }) => {
  await page.goto("/runs");
  await page
    .getByRole("button", { name: /Recent activity/ })
    .click();

  // The awaiting_approval row carries a link to /runs/<id>. Following it lands on
  // that run's detail view (here the paused run shows its approval gate).
  await page.getByRole("link", { name: /Review and approve/ }).click();
  await expect(page).toHaveURL(/\/runs\/awaiting-approval-fixture$/);
  await expect(
    page.getByText("This run is paused for your approval"),
  ).toBeVisible();
});
