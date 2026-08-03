import { test, expect } from "@playwright/test";

import { OUTCOME_META } from "../components/run/repair-timeline";

// The repair surfaces must not overclaim. Three defects motivated these tests:
//
//   1. `wasRepaired` (lib/derive.ts) was `repair_history.length > 0`, so the runs
//      table's "Repaired" badge fired for ANY recorded step -- including a step
//      that applied no patch. A green run carrying the engine's one
//      `qc_verdict_flagged` step would claim a repair that never happened, and so
//      would a pre-existing `gave_up` step (patch null).
//   2. Narrowing that to `patch !== null` still meant a patch was *proposed*, not
//      applied: five self-heal paths record a non-null patch and return before
//      `apply_patch` is ever called, so a user who REJECTED a patch at the
//      approval gate was told their run was "Repaired". The badge now means what
//      it says -- a patch was applied -- because it reads the engine's structured
//      `RepairStep.patch_applied`, which is derived from control flow rather than
//      inferred from the outcome string. "Applied" here is the engine's own
//      meaning: the patch was ENACTED and the loop proceeded to retry. It is not
//      "the patch worked" (see reproduce's `retry_failed`, which is applied and
//      still failed) and not "the config was mutated" (a `retry` patch mutates
//      nothing; the re-run is the fix).
//   3. OUTCOME_META (components/run/repair-timeline.tsx) mapped only three
//      outcomes -- one of them (`stopped_for_confirmation`) emitted nowhere in
//      src/ -- and fell back to `OUTCOME_META.gave_up.className` for anything
//      else, so live literals rendered a raw snake_case label dressed in give-up
//      styling. `rejected_by_user` in give-up grey reads as though the engine
//      failed, when in fact the human declined.
//
// Assertion discipline: the user-visible text is the contract (exact:true, so the
// mangled "Qc Anomaly" auto-title-case does not satisfy "QC anomaly"). For every
// give-up distinctness claim we assert the NEGATIVE -- that the two badges'
// classes DIFFER -- rather than pinning a Tailwind string, which would test the
// stylesheet rather than the behaviour, and would go vacuous on any restyle.

// Every outcome literal the engine emits: 15 recorded by src/contig/self_heal.py,
// 3 by src/contig/verification/reproduce.py (which shares the RepairStep type via
// ReproduceRecord.repair_history). Grouped by what actually happened to the patch.
//
// This list is hand-maintained and is NOT the durability story -- `patch_applied`
// is, because the engine derives it from control flow, so a literal added at an
// existing recording site is already correct without touching any map. What this
// list buys is the *presentation*: it fails loudly if a literal is added upstream
// and nobody gives it prose here, which is how `rejected_by_user` came to render
// as raw snake_case in give-up grey.
const APPLIED_OUTCOMES = [
  "patched_and_retried",
  "approved_and_retried",
  "chose_and_retried",
  "built_index_and_retried",
  "recompressed_reference_and_retried",
  "installed_and_retried",
  // Enacted, then unsuccessful. Applied does not mean it worked.
  "retry_failed",
];
const DECLINED_OUTCOMES = [
  "rejected_by_user",
  "approval_timed_out",
  "invalid_choice_rejected",
];
const GAVE_UP_OUTCOMES = [
  "gave_up",
  "gave_up_at_ceiling",
  "index_build_failed",
  "index_unresolvable",
  "reference_recompress_failed",
  "reference_recompress_unresolvable",
  "install_failed",
];
// An advisory (kind="advisory", operation={}) has no machine fix -- only human
// guidance. A human acknowledged it (outside Contig) and asked the loop to
// retry. This is a fifth case, distinct from all three families above: not
// APPLIED (patch_applied is always False for an advisory), not DECLINED (the
// human did not refuse), not GAVE_UP (the loop went on). See
// components/run/repair-timeline.tsx's ACKNOWLEDGED family comment.
const ADVISORY_OUTCOMES = ["advisory_acknowledged_and_retried"];
const LIVE_OUTCOMES = [
  ...APPLIED_OUTCOMES,
  ...DECLINED_OUTCOMES,
  ...GAVE_UP_OUTCOMES,
  ...ADVISORY_OUTCOMES,
  // A finding on a green run: outside all three families, and already covered by
  // its own tests below.
  "qc_verdict_flagged",
];

/** The outcome badge in the repair timeline: the element carrying the styling. */
function outcomeBadge(page: import("@playwright/test").Page, label: string) {
  return page.locator("span.font-medium").filter({ hasText: label }).first();
}

/** Open a run's Self-heal tab and wait until `expectLabel`'s badge is really there.
 *  The run page is server-rendered, so the tab exists before React has hydrated
 *  and an early click is swallowed silently (reliably so on testpass2, whose 234
 *  events make for a heavy page). Retrying the click until the panel content
 *  appears is attribute-agnostic and beats guessing at a "selected" state hook. */
async function openSelfHealTab(
  page: import("@playwright/test").Page,
  id: string,
  expectLabel: string,
) {
  await page.goto(`/runs/${id}`);
  await expect(page.getByRole("heading", { name: id })).toBeVisible();
  const tab = page.getByRole("tab", { name: /Self-heal/ });
  await expect(async () => {
    await tab.click();
    await expect(outcomeBadge(page, expectLabel)).toBeVisible({ timeout: 1000 });
  }).toPass({ timeout: 20000 });
}

function runRow(page: import("@playwright/test").Page, id: string) {
  return page.getByRole("row").filter({ hasText: id });
}

test("every live outcome literal has prose, and none renders as snake_case", () => {
  // The DOM tests below can only reach the four literals the fixtures carry. This
  // covers the other fourteen at the source of the defect: an unmapped literal is
  // rendered verbatim by the fallback, so "mapped" and "not snake_case" together
  // are exactly the guarantee.
  expect(LIVE_OUTCOMES.length).toBe(19);
  for (const outcome of LIVE_OUTCOMES) {
    const meta = OUTCOME_META[outcome];
    expect(meta, `${outcome} is not mapped in OUTCOME_META`).toBeDefined();
    expect(meta.label, `${outcome} renders as a raw literal`).not.toContain("_");
  }

  // The dead key is gone: it was emitted nowhere in src/ and could never render.
  expect(OUTCOME_META.stopped_for_confirmation).toBeUndefined();
  expect(Object.keys(OUTCOME_META).sort()).toEqual([...LIVE_OUTCOMES].sort());
});

test("the outcome families are visually distinct from each other", () => {
  // Declined must not read as a give-up (the engine did not fail), and applied
  // must not read as either. Asserted as inequality between the families' own
  // tokens rather than against pinned Tailwind strings, so a restyle cannot make
  // it vacuous -- the same discipline the DOM comparisons below use.
  const classOf = (o: string) => OUTCOME_META[o].className;
  const applied = classOf(APPLIED_OUTCOMES[0]);
  const declined = classOf(DECLINED_OUTCOMES[0]);
  const gaveUp = classOf(GAVE_UP_OUTCOMES[0]);
  const advisory = classOf(ADVISORY_OUTCOMES[0]);

  expect(declined).not.toEqual(gaveUp);
  expect(applied).not.toEqual(gaveUp);
  expect(applied).not.toEqual(declined);
  // The advisory/acknowledged family must not collapse into any of the three:
  // not applied (nothing was enacted), not declined (the human did not refuse),
  // not gave-up (the loop went on, not stopped).
  expect(advisory).not.toEqual(applied);
  expect(advisory).not.toEqual(declined);
  expect(advisory).not.toEqual(gaveUp);

  // And each family is internally consistent, so a new member cannot quietly
  // land in the wrong one.
  for (const o of APPLIED_OUTCOMES) expect(classOf(o)).toEqual(applied);
  for (const o of DECLINED_OUTCOMES) expect(classOf(o)).toEqual(declined);
  for (const o of GAVE_UP_OUTCOMES) expect(classOf(o)).toEqual(gaveUp);
  for (const o of ADVISORY_OUTCOMES) expect(classOf(o)).toEqual(advisory);

  // qc_verdict_flagged is none of these, and must not borrow their styling --
  // in particular it must not reuse the advisory/acknowledged colour either.
  const flagged = classOf("qc_verdict_flagged");
  expect(flagged).not.toEqual(applied);
  expect(flagged).not.toEqual(declined);
  expect(flagged).not.toEqual(gaveUp);
  expect(flagged).not.toEqual(advisory);
});

test("a green QC-flagged run does not claim a repair", async ({ page }) => {
  // Nothing was patched: the engine only recorded that QC reduced to fail.
  await page.goto("/runs");
  const row = runRow(page, "qc-anomaly-fixture");
  await expect(row).toBeVisible();
  await expect(row.getByText("Repaired", { exact: true })).toHaveCount(0);
});

test("a give-up that patched nothing does not claim a repair", async ({ page }) => {
  // Pre-existing misstatement, fixed deliberately: testpass2 carries one
  // `gave_up` step with patch null. No patch was applied, so no repair happened.
  await page.goto("/runs");
  const row = runRow(page, "testpass2");
  await expect(row).toBeVisible();
  await expect(row.getByText("Repaired", { exact: true })).toHaveCount(0);
});

test("a run whose only patch was rejected does not claim a repair", async ({
  page,
}) => {
  // The sharp case, and the one `patch !== null` got wrong: the engine proposed a
  // destructive reference patch, the user rejected it at the approval gate, and
  // nothing was enacted. A non-null patch is on the record; patch_applied is not.
  await page.goto("/runs");
  const row = runRow(page, "rejected-patch-fixture");
  await expect(row).toBeVisible();
  await expect(row.getByText("Repaired", { exact: true })).toHaveCount(0);
});

test("a run whose only step was an advisory does not claim a repair", async ({
  page,
}) => {
  // The engine has no machine fix for an advisory -- only guidance -- so
  // patch_applied is always False here, the same as a rejected patch. Nothing
  // was enacted, so this must not read as Repaired.
  await page.goto("/runs");
  const row = runRow(page, "advisory-fixture");
  await expect(row).toBeVisible();
  await expect(row.getByText("Repaired", { exact: true })).toHaveCount(0);
});

test("a run whose patch was applied still claims a repair", async ({ page }) => {
  // The positive control. Without it, a `wasRepaired` that always returned false
  // would satisfy both assertions above.
  await page.goto("/runs");
  const row = runRow(page, "qc-anomaly-patched-fixture");
  await expect(row).toBeVisible();
  await expect(row.getByText("Repaired", { exact: true })).toHaveCount(1);
});

test("the QC-verdict flag renders its own outcome and failure labels", async ({
  page,
}) => {
  await openSelfHealTab(page, "qc-anomaly-fixture", "QC verdict flagged");

  // Not the raw literal, and not the auto-title-cased "Qc Anomaly".
  await expect(page.getByText("QC verdict flagged", { exact: true })).toBeVisible();
  await expect(page.getByText("QC anomaly", { exact: true })).toBeVisible();
  await expect(page.getByText("qc_verdict_flagged", { exact: true })).toHaveCount(0);
  await expect(page.getByText("Qc Anomaly", { exact: true })).toHaveCount(0);

  // It recorded no patch, and says so rather than implying one.
  await expect(page.getByText("No automatic patch.")).toBeVisible();
});

test("the QC-verdict flag is not styled as a give-up", async ({ page }) => {
  // The exact defect: an unmapped outcome fell through to gave_up's className.
  // Comparing the two rendered badges keeps this honest under any restyle -- it
  // fails iff the two share styling, and can never pass vacuously.
  await openSelfHealTab(page, "testpass2", "Gave up");
  const gaveUp = await outcomeBadge(page, "Gave up").getAttribute("class");
  expect(gaveUp).not.toBeNull();

  await openSelfHealTab(page, "qc-anomaly-fixture", "QC verdict flagged");
  const flagged = await outcomeBadge(page, "QC verdict flagged").getAttribute("class");
  expect(flagged).not.toBeNull();

  expect(flagged).not.toEqual(gaveUp);
});

test("a rejected patch reads as a human decision, not a raw literal", async ({
  page,
}) => {
  await openSelfHealTab(page, "rejected-patch-fixture", "You rejected this fix");

  // Prose, not the machine literal that used to fall through OUTCOME_META.
  await expect(page.getByText("You rejected this fix", { exact: true })).toBeVisible();
  await expect(page.getByText("rejected_by_user", { exact: true })).toHaveCount(0);

  // The patch itself is still on the record -- proposed is not the same as gone.
  await expect(page.getByText("No automatic patch.")).toHaveCount(0);
  await expect(page.getByText("risk: destructive")).toBeVisible();
});

test("a declined patch is not styled as a give-up", async ({ page }) => {
  // The engine did not fail here; the human declined. Same negative-comparison
  // discipline as the QC-flag case above: it fails iff the two share styling.
  //
  // The give-up badge is read from giveup-fixture, not testpass2, deliberately.
  // testpass2's record is 99KB with 234 events, and two specs opening that page
  // concurrently under the suite's parallelism time each other out -- reliably
  // enough to fail the suite, and reliably enough that pointing this one at a
  // small record makes it pass. The assertion is identical either way: both runs
  // render the same `gave_up` literal through the same OUTCOME_META entry.
  await openSelfHealTab(page, "giveup-fixture", "Gave up");
  const gaveUp = await outcomeBadge(page, "Gave up").getAttribute("class");
  expect(gaveUp).not.toBeNull();

  await openSelfHealTab(page, "rejected-patch-fixture", "You rejected this fix");
  const rejected = await outcomeBadge(page, "You rejected this fix").getAttribute(
    "class",
  );
  expect(rejected).not.toBeNull();

  expect(rejected).not.toEqual(gaveUp);
});

test("an advisory renders as acknowledged guidance, not a raw literal or a patch", async ({
  page,
}) => {
  await openSelfHealTab(
    page,
    "advisory-fixture",
    "You acknowledged this guidance; retried",
  );

  // Prose, not the machine literal.
  await expect(
    page.getByText("You acknowledged this guidance; retried", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("advisory_acknowledged_and_retried", { exact: true }),
  ).toHaveCount(0);

  // The guidance itself is on the record...
  await expect(
    page.getByText(
      "Out of disk; clean the work directory to reclaim space, then retry.",
      { exact: true },
    ),
  ).toBeVisible();

  // ...but the empty operation ({}) must render as nothing, not the literal
  // "{}" -- rendering it would read as "an empty change was applied".
  await expect(page.getByText("{}", { exact: true })).toHaveCount(0);
});

test("a real patch and a QC flag keep their own outcome labels side by side", async ({
  page,
}) => {
  await openSelfHealTab(page, "qc-anomaly-patched-fixture", "QC verdict flagged");

  await expect(page.getByText("Patched and retried", { exact: true })).toBeVisible();
  await expect(page.getByText("QC verdict flagged", { exact: true })).toBeVisible();

  const patched = await outcomeBadge(page, "Patched and retried").getAttribute("class");
  const flagged = await outcomeBadge(page, "QC verdict flagged").getAttribute("class");
  expect(flagged).not.toEqual(patched);
});
