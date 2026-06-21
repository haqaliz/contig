import { test, expect } from "@playwright/test";
import { promises as fs } from "fs";
import path from "path";

// The runs directory the dev server reads (matches lib/runs runsDir default).
const runsDir = path.resolve(process.cwd(), "..", "runs");
const FIXTURE = "e2e-running-fixture";

test("run list shows the Run test profile button", async ({ page }) => {
  // We assert the button is present but do NOT click it (clicking would spawn a
  // real pipeline run). The running view is covered by the fixture test below.
  await page.goto("/runs");
  await expect(
    page.getByRole("button", { name: /Run test profile/ }),
  ).toBeVisible();
});

test("an in-progress run shows the running view, not a 404", async ({ page }) => {
  const dir = path.join(runsDir, FIXTURE);
  await fs.mkdir(dir, { recursive: true });
  await fs.writeFile(
    path.join(dir, "status.json"),
    JSON.stringify({
      run_id: FIXTURE,
      state: "running",
      started_at: new Date().toISOString(),
      finished_at: null,
      pid: 1,
    }),
  );
  try {
    await page.goto(`/runs/${FIXTURE}`);
    await expect(page.getByText(/in progress/i)).toBeVisible();
  } finally {
    await fs.rm(dir, { recursive: true, force: true });
  }
});
