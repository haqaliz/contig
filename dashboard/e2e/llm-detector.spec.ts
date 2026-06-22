import { test, expect } from "@playwright/test";

// The LLM detector in the /eval selector (PRD contract A/C). The optional,
// provider-agnostic LLM detector ("llm") is offered alongside rules and
// rules-strict. Selecting it drives ?detector=llm so the server scores it. When
// no provider/key is configured the engine returns the graceful not-available
// branch, which the page already renders; the selector itself is the contract
// tested here (the detector's report is covered by the engine suite).

test("the detector selector offers the llm option", async ({ page }) => {
  await page.goto("/eval");

  await page.getByRole("combobox", { name: "Detector" }).click();
  await expect(
    page.getByRole("option", { name: "LLM (needs a key)" }),
  ).toBeVisible();
});

test("choosing the llm detector drives the ?detector=llm query", async ({
  page,
}) => {
  await page.goto("/eval");

  await page.getByRole("combobox", { name: "Detector" }).click();
  await page.getByRole("option", { name: "LLM (needs a key)" }).click();

  await expect(page).toHaveURL(/\/eval\?detector=llm$/);
  await expect(
    page.getByRole("combobox", { name: "Detector" }),
  ).toContainText("LLM (needs a key)");
  // The page degrades gracefully rather than erroring: the selector still reads
  // "llm" and the page renders. (Whether the live report or the not-available
  // notice shows depends on the engine env; both are valid graceful branches, so
  // we pin only the selector contract here.)
  await expect(page.getByRole("combobox", { name: "Detector" })).toBeVisible();
});
