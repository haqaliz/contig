import { test, expect } from "@playwright/test";

// The pending-review surface. This asserts the page loads and shows its heading,
// which holds whether the pending corpus is empty (positive empty state) or has
// auto-captured failure cases waiting for human confirmation.

test("pending review page loads and shows its heading", async ({ page }) => {
  await page.goto("/pending");
  await expect(page.getByRole("heading", { name: /Pending/ })).toBeVisible();
});
