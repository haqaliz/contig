// Synthetic run fixtures used by the e2e suite (awaiting-approval, cancelled,
// live, reproduce, verify, scrnaseq, and so on). They live here, NOT in the real
// runs directory, so they never clutter a user's dashboard. The global setup
// copies them into the runs directory before the suite and the teardown removes
// them after, so they exist only while the tests run. This includes the baseline
// bundles testpass2 (nf-core/rnaseq, pass) and variant-bad (nf-core/sarek, fail):
// they used to be expected as permanent bundles in the gitignored runs directory,
// which meant they were absent in CI and the suite failed there. They are managed
// fixtures now so the suite is self-contained.
import { cpSync, rmSync, existsSync, renameSync } from "fs";
import path from "path";

// The fixture run ids this suite provisions. Each is a directory under
// e2e/fixtures/<id> that is copied to <runsDir>/<id>.
export const FIXTURE_RUN_IDS = [
  // Baseline bundles the smoke, explain, reproduce, and compare specs read by id.
  // run_record.json only (no heavy results/.nextflow/work), which is all the
  // dashboard renders for these tests.
  "testpass2",
  "variant-bad",
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
  // A finished run whose record carries concordance QC results (kind
  // "concordance"): one passing cross-tool agreement check and one "unverified"
  // check (no second tool to compare against), for the concordance section in the
  // QC panel (a dedicated cross-tool corroboration section, separate from metric
  // and structural checks) and for the neutral "unverified" status pill.
  "concordance-fixture",
  // A dual-annotated variant run (nf-core/sarek) carrying VEP+SnpEff
  // annotation_identity and both consequence_concordance and
  // gene_symbol_concordance QC results (kind "concordance"), for the
  // "Corroborated by ..." line + annotation cache/build note in the concordance
  // card (C7 M5). The single-annotator counterpart below carries a
  // consequence_concordance with value null, so the line is omitted (PRD D2).
  "corroboration-fixture",
  "corroboration-absent-fixture",
  // A finished run (numeric QC metrics) for the cross-run benchmark section (PRD
  // contract A). The benchmark route is mocked in the spec to return a drift report
  // and a no_reference report, so the section renders deterministically without the
  // engine's benchmark CLI in the test environment.
  "benchmark-fixture",
  // A paused run whose pending_approval.json carries an options array with
  // decision_kind "choice" (PRD contract D), for the guided-escalation choice gate.
  // The approve route is mocked in the spec so the chosen index is asserted without
  // the real CLI.
  "choice-fixture",
  // A finished run whose owner.json carries a workspace tag (PRD section A): owned
  // by a non-admin (auth0|bob) and shared into the "lab-x" workspace. Under the
  // bypass the admin sees it like any run; the cross-user and workspace-shared
  // denial paths are covered by the unit-level ownership-filter spec.
  "workspace-fixture",
  // A finished run (no failed tasks) whose qc_results are ALL "unverified" (PRD
  // verdict-neutral-informational-checks): proves overallQc/explainVerdict have a
  // real unverified arm instead of falling through to a false "PASS: all N checks
  // passed" (see e2e/unverified-verdict.spec.ts).
  "unverified-fixture",
  // A finished run whose qc_results mix one "informational" pass (asserts
  // nothing, so it must not manufacture a pass) with "unverified" siblings: proves
  // overallQc skips informational results rather than letting them drive the
  // reduction to "pass" (see e2e/unverified-verdict.spec.ts).
  "informational-only-fixture",
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

// The holdout-accuracy history (C6 self-heal regression guard) the /eval trend
// reads (HoldoutHistory). Mirrors evalHistoryPath() handling above: back up any
// real file, swap in a fixture with >=2 snapshots so a delta renders, and
// restore the real file on teardown. Mirrors lib/runs.ts holdoutHistoryPath():
// CONTIG_HOLDOUT_HISTORY, else <repoRoot>/src/contig/data/holdout_history.jsonl.
function holdoutHistoryPath(): string {
  return process.env.CONTIG_HOLDOUT_HISTORY
    ? path.resolve(process.env.CONTIG_HOLDOUT_HISTORY)
    : path.resolve(
        process.cwd(),
        "..",
        "src",
        "contig",
        "data",
        "holdout_history.jsonl",
      );
}
function holdoutHistoryBackupPath(): string {
  return `${holdoutHistoryPath()}.e2e-backup`;
}
function holdoutHistoryFixture(): string {
  return path.join(fixturesDir(), "_holdout_history", "holdout_history.jsonl");
}

// The self-heal outcome-match history (C6 self-heal regression guard) the
// /eval trend reads (HealHistory). Same backup->swap->restore handling.
// Mirrors lib/runs.ts healHistoryPath(): CONTIG_HEAL_HISTORY, else
// <repoRoot>/src/contig/data/heal_history.jsonl.
function healHistoryPath(): string {
  return process.env.CONTIG_HEAL_HISTORY
    ? path.resolve(process.env.CONTIG_HEAL_HISTORY)
    : path.resolve(
        process.cwd(),
        "..",
        "src",
        "contig",
        "data",
        "heal_history.jsonl",
      );
}
function healHistoryBackupPath(): string {
  return `${healHistoryPath()}.e2e-backup`;
}
function healHistoryFixture(): string {
  return path.join(fixturesDir(), "_heal_history", "heal_history.jsonl");
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

  // Provision the holdout-accuracy history the same way: back up any real file,
  // then swap in the fixture so the held-out trend renders.
  const liveHoldout = holdoutHistoryPath();
  if (existsSync(liveHoldout)) renameSync(liveHoldout, holdoutHistoryBackupPath());
  if (existsSync(holdoutHistoryFixture())) {
    cpSync(holdoutHistoryFixture(), liveHoldout);
  }

  // Provision the self-heal outcome-match history the same way: back up any
  // real file, then swap in the fixture so the heal trend renders.
  const liveHeal = healHistoryPath();
  if (existsSync(liveHeal)) renameSync(liveHeal, healHistoryBackupPath());
  if (existsSync(healHistoryFixture())) {
    cpSync(healHistoryFixture(), liveHeal);
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

  // Remove the fixture holdout history, then restore any real one we moved aside.
  rmSync(holdoutHistoryPath(), { force: true });
  const holdoutBackup = holdoutHistoryBackupPath();
  if (existsSync(holdoutBackup)) renameSync(holdoutBackup, holdoutHistoryPath());

  // Remove the fixture heal history, then restore any real one we moved aside.
  rmSync(healHistoryPath(), { force: true });
  const healBackup = healHistoryBackupPath();
  if (existsSync(healBackup)) renameSync(healBackup, healHistoryPath());
}
