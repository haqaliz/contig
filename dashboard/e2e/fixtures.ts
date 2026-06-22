// Synthetic run fixtures used by the e2e suite (awaiting-approval, cancelled,
// live, reproduce, verify, scrnaseq, and so on). They live here, NOT in the real
// runs directory, so they never clutter a user's dashboard. The global setup
// copies them into the runs directory before the suite and the teardown removes
// them after, so they exist only while the tests run. Real run bundles (testpass2,
// variant-bad) stay in the runs directory permanently and are not managed here.
import { cpSync, rmSync, existsSync, renameSync } from "fs";
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
  // A finished run with recorded output_checksums whose file is present on disk,
  // so `contig verify` reports ok (the output-integrity badge, PRD contract B).
  "verify-fixture",
  // A scRNA-seq run bundle (nf-core/scrnaseq) that renders in the existing
  // run/verdict/QC views with no special UI (PRD contract D).
  "scrnaseq-fixture",
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

// The notifications feed (PRD contract A) reads a single file at the runs-dir
// root, not inside a run dir, so it is provisioned separately. We back up any
// real notifications.jsonl first and restore it on teardown, so a user's own
// feed is never overwritten or lost by the suite.
function notificationsPath(): string {
  return path.join(runsDir(), "notifications.jsonl");
}
function notificationsBackupPath(): string {
  return path.join(runsDir(), "notifications.jsonl.e2e-backup");
}
function notificationsFixture(): string {
  return path.join(fixturesDir(), "_notifications", "notifications.jsonl");
}

export function installFixtures(): void {
  const dest = runsDir();
  for (const id of FIXTURE_RUN_IDS) {
    const from = path.join(fixturesDir(), id);
    if (!existsSync(from)) continue;
    cpSync(from, path.join(dest, id), { recursive: true });
  }

  // Provision the notifications feed at the runs-dir root. If a real one exists,
  // move it aside first so teardown can put it back untouched.
  const live = notificationsPath();
  if (existsSync(live)) renameSync(live, notificationsBackupPath());
  if (existsSync(notificationsFixture())) {
    cpSync(notificationsFixture(), live);
  }
}

export function removeFixtures(): void {
  const dest = runsDir();
  for (const id of FIXTURE_RUN_IDS) {
    rmSync(path.join(dest, id), { recursive: true, force: true });
  }

  // Remove the fixture feed, then restore any real one we moved aside.
  rmSync(notificationsPath(), { force: true });
  const backup = notificationsBackupPath();
  if (existsSync(backup)) renameSync(backup, notificationsPath());
}
