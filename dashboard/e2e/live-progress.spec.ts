import { test, expect } from "@playwright/test";

// The live progress view polls /api/runs/[id]/progress and renders a summary:
// elapsed time, tasks completed, currently-running steps, live self-heal
// attempts, and a collapsible log tail. The fixture run dir runs/live-fixture
// renders as "running" because its status.json carries pid 1: process.kill(1, 0)
// throws EPERM, which isLive() treats as alive (see lib/runs isProcessAlive).

const FIXTURE = "live-fixture";

test("the live view shows progress, running steps, and a self-heal attempt", async ({
  page,
}) => {
  await page.goto(`/runs/${FIXTURE}`);

  // It is the running view, not a 404 and not the finished detail.
  await expect(page.getByText(/in progress/i)).toBeVisible();

  // The trace fixture has one COMPLETED row, so the completed count reads 1.
  await expect(page.getByText("Tasks completed")).toBeVisible();

  // The RUNNING row surfaces as a currently-running step (STAR_ALIGN).
  await expect(page.getByText(/Currently running/)).toBeVisible();
  await expect(page.getByText(/STAR_ALIGN/).first()).toBeVisible();

  // The repair_progress.jsonl line surfaces as a live self-heal attempt.
  await expect(page.getByText(/Self-healing in progress/)).toBeVisible();
  await expect(page.getByText("Attempt 1")).toBeVisible();
  await expect(page.getByText("Out of memory")).toBeVisible();
});

test("the log tail is collapsible: a handle opens and closes it", async ({
  page,
}) => {
  await page.goto(`/runs/${FIXTURE}`);

  // The tail starts collapsed: the handle reads "Show log tail".
  const openHandle = page.getByRole("button", { name: "Show log tail" });
  await expect(openHandle).toBeVisible();

  // Opening it reveals the log lines (ANSI stripped: the raw escape is gone).
  await openHandle.click();
  await expect(page.getByText(/Launching nf-core\/rnaseq/)).toBeVisible();

  // The handle now offers to close it again (the noisy log can be calmed).
  const closeHandle = page.getByRole("button", { name: "Hide log tail" });
  await expect(closeHandle).toBeVisible();
  await closeHandle.click();
  await expect(
    page.getByRole("button", { name: "Show log tail" }),
  ).toBeVisible();
});
