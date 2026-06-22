import { test, expect } from "@playwright/test";

// Self-heal confirm gate (PRD feature 2). When a run is paused (status
// awaiting_approval, pid 1) the live view leads with the approval gate: it shows
// the proposed patch (kind, risk, rationale) and the diagnosis it answers, with
// Approve and Reject. A destructive patch requires a SECOND confirm before the
// approve POST fires. We mock the approve route so the wiring is exercised without
// the real CLI.

test("a paused run shows the proposed patch and its diagnosis", async ({
  page,
}) => {
  await page.goto("/runs/awaiting-approval-fixture");

  await expect(
    page.getByText("This run is paused for your approval"),
  ).toBeVisible();

  // The diagnosis the patch answers (failure class label + root cause).
  await expect(page.getByText("Missing reference")).toBeVisible();
  await expect(
    page.getByText(/needs a reference genome that is not on this machine/),
  ).toBeVisible();

  // The patch: kind, risk, rationale.
  await expect(page.getByText("reference", { exact: true })).toBeVisible();
  await expect(page.getByText("destructive").first()).toBeVisible();
  await expect(
    page.getByText(/Fetch the GRCh38 reference and re-run/),
  ).toBeVisible();

  await expect(page.getByRole("button", { name: "Approve" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Reject" })).toBeVisible();
});

test("a destructive patch needs a second confirm before Approve fires", async ({
  page,
}) => {
  let approvedBody: string | null = null;
  await page.route("**/api/runs/awaiting-approval-fixture/approve", async (route) => {
    approvedBody = route.request().postData() ?? "";
    await route.fulfill({
      status: 202,
      contentType: "application/json",
      body: JSON.stringify({ ok: true, decision: "approve" }),
    });
  });

  await page.goto("/runs/awaiting-approval-fixture");

  // First click arms the confirm step (it does NOT POST yet).
  await page.getByRole("button", { name: "Approve" }).click();
  await expect(
    page.getByRole("button", { name: "Confirm destructive approve" }),
  ).toBeVisible();
  expect(approvedBody).toBeNull();

  // Second click sends the approve decision.
  await page.getByRole("button", { name: "Confirm destructive approve" }).click();
  await expect.poll(() => approvedBody).toContain("approve");
});

test("a needs_confirmation patch approves on a single click", async ({
  page,
}) => {
  let approvedBody: string | null = null;
  await page.route("**/api/runs/awaiting-confirm-fixture/approve", async (route) => {
    approvedBody = route.request().postData() ?? "";
    await route.fulfill({
      status: 202,
      contentType: "application/json",
      body: JSON.stringify({ ok: true, decision: "approve" }),
    });
  });

  await page.goto("/runs/awaiting-confirm-fixture");

  await expect(page.getByText("needs confirmation").first()).toBeVisible();

  // Not destructive, so a single Approve click fires the POST (no confirm step).
  await page.getByRole("button", { name: "Approve" }).click();
  await expect.poll(() => approvedBody).toContain("approve");
});

test("Reject POSTs a reject decision", async ({ page }) => {
  let rejectBody: string | null = null;
  await page.route("**/api/runs/awaiting-confirm-fixture/approve", async (route) => {
    rejectBody = route.request().postData() ?? "";
    await route.fulfill({
      status: 202,
      contentType: "application/json",
      body: JSON.stringify({ ok: true, decision: "reject" }),
    });
  });

  await page.goto("/runs/awaiting-confirm-fixture");
  await page.getByRole("button", { name: "Reject" }).click();

  await expect.poll(() => rejectBody).toContain("reject");
});
