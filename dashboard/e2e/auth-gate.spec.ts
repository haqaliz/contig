import { test, expect } from "@playwright/test";

// Auth gate under the dev/test bypass (PRD contract C). The suite runs with
// CONTIG_AUTH_DISABLED=1, so the proxy is a no-op: every route is reachable
// without a real Auth0 tenant, and the caller is treated as an admin. This spec
// pins that bypass behavior, which is exactly what keeps local dev and CI green.

test("with auth disabled, protected routes load without a login redirect", async ({
  page,
}) => {
  // No redirect to /auth/login: the runs list renders directly.
  await page.goto("/runs");
  await expect(page).toHaveURL(/\/runs$/);
  await expect(page.getByRole("navigation", { name: "Primary" })).toBeVisible();
});

test("with auth disabled, the header shows the local admin account", async ({
  page,
}) => {
  await page.goto("/runs");

  // The account menu reads "Local admin" (the synthetic bypass user). Opening it
  // shows the admin role and, because there is no real session, no logout link.
  const account = page.getByRole("button", { name: "Account" });
  await expect(account).toBeVisible();
  await expect(account).toContainText("Local admin");

  await account.click();
  await expect(page.getByText("Role: admin")).toBeVisible();
  await expect(page.getByRole("menuitem", { name: "Log out" })).toHaveCount(0);
});

test("with auth disabled, a write action route is allowed (admin)", async ({
  request,
}) => {
  // The corpus-promote action requires the writer/admin role. Under the bypass
  // the caller is an admin, so the route is NOT 401/403; it proceeds to its own
  // validation and returns a 400 for a missing case_id (proving the gate passed,
  // not a 403 from the authorization guard).
  const res = await request.post("/api/corpus/promote", {
    data: {},
  });
  expect(res.status()).not.toBe(401);
  expect(res.status()).not.toBe(403);
  expect(res.status()).toBe(400);
});
