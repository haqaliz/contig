import { test, expect } from "@playwright/test";

// Guided-escalation choice gate (PRD contract D). When pending_approval.json has an
// options array with decision_kind "choice", the gate renders the ranked fixes as a
// single-select list. The human picks one, then Approve sends the chosen index
// (`contig approve --choose N`). A destructive selected option still needs a second
// confirm. We mock the approve route so the chosen index is asserted without the CLI.

test("a choice decision renders the ranked options and pre-selects the best", async ({
  page,
}) => {
  await page.goto("/runs/choice-fixture");

  await expect(
    page.getByText("This run is paused for your approval"),
  ).toBeVisible();
  await expect(
    page.getByText(/The diagnosis was ambiguous/),
  ).toBeVisible();

  // The diagnosis the choice answers.
  await expect(page.getByText("Out of memory", { exact: true })).toBeVisible();

  // All three ranked options are present, by their rationale.
  await expect(
    page.getByText(/Raise the memory cap to 12 GB/),
  ).toBeVisible();
  await expect(
    page.getByText(/Lower the thread count/),
  ).toBeVisible();
  await expect(
    page.getByText(/Rebuild the aligner index from scratch/),
  ).toBeVisible();

  // The first (best) option is pre-selected.
  const options = page.getByRole("button", { pressed: true });
  await expect(options).toHaveCount(1);
});

test("Approve sends the selected option index", async ({ page }) => {
  let approvedBody: string | null = null;
  await page.route("**/api/runs/choice-fixture/approve", async (route) => {
    approvedBody = route.request().postData() ?? "";
    await route.fulfill({
      status: 202,
      contentType: "application/json",
      body: JSON.stringify({ ok: true, decision: "approve", choice: 1 }),
    });
  });

  await page.goto("/runs/choice-fixture");

  // Pick the second option (a non-destructive needs_confirmation), then Approve.
  await page.getByText(/Lower the thread count/).click();
  await page.getByRole("button", { name: "Approve selected" }).click();

  await expect.poll(() => approvedBody).toContain('"choice":1');
  await expect.poll(() => approvedBody).toContain('"decision":"approve"');
});

test("a destructive selected option needs a second confirm", async ({ page }) => {
  let approvedBody: string | null = null;
  await page.route("**/api/runs/choice-fixture/approve", async (route) => {
    approvedBody = route.request().postData() ?? "";
    await route.fulfill({
      status: 202,
      contentType: "application/json",
      body: JSON.stringify({ ok: true, decision: "approve", choice: 2 }),
    });
  });

  await page.goto("/runs/choice-fixture");

  // Pick the third option (destructive: rebuild the index).
  await page.getByText(/Rebuild the aligner index from scratch/).click();

  // First Approve click arms the confirm step and does NOT POST yet.
  await page.getByRole("button", { name: "Approve selected" }).click();
  await expect(
    page.getByRole("button", { name: "Confirm destructive approve" }),
  ).toBeVisible();
  expect(approvedBody).toBeNull();

  // Second click sends the destructive choice with its index.
  await page.getByRole("button", { name: "Confirm destructive approve" }).click();
  await expect.poll(() => approvedBody).toContain('"choice":2');
});

test("Reject POSTs a reject decision with no choice", async ({ page }) => {
  let rejectBody: string | null = null;
  await page.route("**/api/runs/choice-fixture/approve", async (route) => {
    rejectBody = route.request().postData() ?? "";
    await route.fulfill({
      status: 202,
      contentType: "application/json",
      body: JSON.stringify({ ok: true, decision: "reject" }),
    });
  });

  await page.goto("/runs/choice-fixture");
  await page.getByRole("button", { name: "Reject" }).click();

  await expect.poll(() => rejectBody).toContain("reject");
  expect(rejectBody).not.toContain("choice");
});
