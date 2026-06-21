import { test, expect } from "@playwright/test";
import { promises as fs } from "fs";
import path from "path";

// The pending-review surface. This asserts the page loads and shows its heading,
// which holds whether the pending corpus is empty (positive empty state) or has
// auto-captured failure cases waiting for human confirmation.

const runsDir = path.resolve(process.cwd(), "..", "runs");
const pendingFile = path.join(runsDir, "pending_corpus.jsonl");

test("pending review page loads and shows its heading", async ({ page }) => {
  await page.goto("/pending");
  await expect(page.getByRole("heading", { name: /Pending/ })).toBeVisible();
});

test("a pending case shows confirm and correct actions", async ({ page }) => {
  // Back up any real pending corpus, drop in a fixture, then restore. We never
  // click the actions (that would promote into the golden corpus); we only
  // assert they render.
  let backup: string | null = null;
  try {
    backup = await fs.readFile(pendingFile, "utf8");
  } catch {
    backup = null;
  }
  const fixture = {
    case_id: "e2e-pending-1",
    description: "fixture",
    source: "pending:e2e",
    events: [{ process: "STAR", status: "FAILED", exit: 1 }],
    log_text: "boom",
    expected_class: "tool_crash",
  };
  await fs.mkdir(runsDir, { recursive: true });
  await fs.writeFile(pendingFile, JSON.stringify(fixture) + "\n");
  try {
    await page.goto("/pending");
    await expect(
      page.getByRole("button", { name: /Confirm tool_crash/ }),
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: /Correct label/ }),
    ).toBeVisible();
  } finally {
    if (backup !== null) await fs.writeFile(pendingFile, backup);
    else await fs.rm(pendingFile, { force: true });
  }
});
