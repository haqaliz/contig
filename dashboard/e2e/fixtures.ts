// Synthetic run fixtures used by the e2e suite (awaiting-approval, cancelled,
// live, reproduce, and so on). They live here, NOT in the real runs directory, so
// they never clutter a user's dashboard. The global setup copies them into the
// runs directory before the suite and the teardown removes them after, so they
// exist only while the tests run. Real run bundles (testpass2, variant-bad) stay
// in the runs directory permanently and are not managed here.
import { cpSync, rmSync, existsSync } from "fs";
import path from "path";

// The fixture run ids this suite provisions. Each is a directory under
// e2e/fixtures/<id> that is copied to <runsDir>/<id>.
export const FIXTURE_RUN_IDS = [
  "awaiting-approval-fixture",
  "awaiting-confirm-fixture",
  "cancelled-fixture",
  "live-fixture",
  "reproduce-fixture",
  "taskfail-fixture",
  "warn-fixture",
];

// Mirror lib/runs.ts runsDir(): CONTIG_RUNS_DIR, else ../runs from the dashboard
// cwd (where Playwright runs).
export function runsDir(): string {
  return process.env.CONTIG_RUNS_DIR
    ? path.resolve(process.env.CONTIG_RUNS_DIR)
    : path.resolve(process.cwd(), "..", "runs");
}

function fixturesDir(): string {
  return path.resolve(process.cwd(), "e2e", "fixtures");
}

export function installFixtures(): void {
  const dest = runsDir();
  for (const id of FIXTURE_RUN_IDS) {
    const from = path.join(fixturesDir(), id);
    if (!existsSync(from)) continue;
    cpSync(from, path.join(dest, id), { recursive: true });
  }
}

export function removeFixtures(): void {
  const dest = runsDir();
  for (const id of FIXTURE_RUN_IDS) {
    rmSync(path.join(dest, id), { recursive: true, force: true });
  }
}
