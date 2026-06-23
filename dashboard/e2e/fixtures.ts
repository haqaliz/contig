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
  // A finished run whose record carries resource_usage (per-task duration, peak
  // memory, cpu), for the resources-and-cost card (PRD contracts A, B).
  "resource-fixture",
  // A finished run bundle used by the provenance export buttons (PRD contract C):
  // the RO-Crate and methods download routes are exercised against this id. The
  // report download button (PRD contract D) is exercised against it too.
  "export-fixture",
  // A finished run carrying an Ed25519 signature.json sidecar (PRD contracts E,
  // F), for the signed/verified badge on the output-integrity card. The verify
  // route is mocked in the spec to report signature_ok, so the badge renders
  // deterministically without the signing toolchain in the test environment.
  "signed-fixture",
  // A finished run whose record carries a structural QC result with status fail
  // and kind "structural" (PRD contracts C, F), for the structural-QC labeling in
  // the QC panel (a dedicated structural section, separate from metric checks).
  "structural-fixture",
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

// The eval-history file the /eval trend AND the detector-comparison view read
// (PRD contract A). We provision a fixture history that carries snapshots tagged
// with two detectors (rules + llm), so the compare view renders rules vs llm side
// by side, without depending on the user's real committed history. We back up the
// real file first and restore it on teardown, so a user's own history is never
// overwritten or lost by the suite. Mirrors lib/runs.ts evalHistoryPath():
// CONTIG_EVAL_HISTORY, else <repoRoot>/src/contig/data/eval_history.jsonl.
function evalHistoryPath(): string {
  return process.env.CONTIG_EVAL_HISTORY
    ? path.resolve(process.env.CONTIG_EVAL_HISTORY)
    : path.resolve(
        process.cwd(),
        "..",
        "src",
        "contig",
        "data",
        "eval_history.jsonl",
      );
}
function evalHistoryBackupPath(): string {
  return `${evalHistoryPath()}.e2e-backup`;
}
function evalHistoryFixture(): string {
  return path.join(fixturesDir(), "_eval_history", "eval_history.jsonl");
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

  // Provision the eval history (tagged by detector) the same way: back up any real
  // file, then swap in the fixture so the trend and the compare view both render.
  const liveEval = evalHistoryPath();
  if (existsSync(liveEval)) renameSync(liveEval, evalHistoryBackupPath());
  if (existsSync(evalHistoryFixture())) {
    cpSync(evalHistoryFixture(), liveEval);
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

  // Remove the fixture eval history, then restore any real one we moved aside.
  rmSync(evalHistoryPath(), { force: true });
  const evalBackup = evalHistoryBackupPath();
  if (existsSync(evalBackup)) renameSync(evalBackup, evalHistoryPath());
}
