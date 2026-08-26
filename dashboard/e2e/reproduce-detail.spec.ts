import { test, expect } from "@playwright/test";

// The per-run audit surface for third-party `contig reproduce` bundles (C8):
// /reproduce/[id] plus the read-only bundle download route. Three fixtures
// (provisioned by global-setup, same as the listing spec):
//   reproduce-mixed      - every claim literal (reproduced, within_tolerance,
//                          diverged, unverified, plus the unknown "suspicious"
//                          probe), one applied env repair (pandas), a signature
//                          sidecar, and full provenance (commit, tree hash,
//                          requested_rev "v1.0").
//   reproduce-unverified - exit code 2: the header reads "Did not complete
//                          (exit 2)", never a claim-status badge; the single
//                          claim stays unverified with its verbatim message.
//   reproduce-empty      - zero claims: an honest "Unverified" non-result.
//
// Hash rendering follows the provenance-panel convention: monospace,
// middle-truncated, with the full value on hover (title attribute).

const MIXED = "reproduce-mixed";
const COMMIT = "0123456789abcdef0123456789abcdef01234567";
const TREE =
  "fedcba9876543210fedcba9876543210fedcba9876543210fedcba9876543210";
const CLAIMS_SHA =
  "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef";

// Each page section is an <section aria-label="...">, so specs scope by role
// region (the qc-panel sample-group convention).
function summary(page: import("@playwright/test").Page) {
  return page.getByRole("region", { name: "Reproduction summary" });
}
function provenance(page: import("@playwright/test").Page) {
  return page.getByRole("region", { name: "Provenance" });
}
function claims(page: import("@playwright/test").Page) {
  return page.getByRole("region", { name: "Claims" });
}
function repairs(page: import("@playwright/test").Page) {
  return page.getByRole("region", { name: "Repair history" });
}
function signature(page: import("@playwright/test").Page) {
  return page.getByRole("region", { name: "Signature" });
}
// The claims-table row whose id cell is the given claim id.
function claimRow(page: import("@playwright/test").Page, id: string) {
  return claims(page)
    .locator("tbody tr")
    .filter({ has: page.getByRole("cell", { name: id, exact: true }) });
}

test("clicking a reproduce row navigates to its detail page", async ({
  page,
}) => {
  await page.goto("/reproduce");
  await page.getByRole("link", { name: MIXED, exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`/reproduce/${MIXED}$`));
  await expect(page.getByRole("heading", { name: MIXED })).toBeVisible();
});

test("the header shows the id, derived overall, repo, command, date, and exit code", async ({
  page,
}) => {
  await page.goto(`/reproduce/${MIXED}`);

  await expect(page.getByRole("heading", { name: MIXED })).toBeVisible();

  // Worst-of over the claim statuses -> diverged, never a claim-status pass.
  const s = summary(page);
  await expect(s.getByText("Diverged", { exact: true })).toBeVisible();
  await expect(s.getByText("https://github.com/example/paper-repo", { exact: true })).toBeVisible();
  await expect(s.getByText("bash run.sh", { exact: true })).toBeVisible();
  // toLocaleDateString() server-side: the same short date the listing renders.
  await expect(s).toContainText("8/20/2026");
  // exit_code 0 renders as a neutral number next to its label.
  await expect(s.getByText("Exit code", { exact: true })).toBeVisible();
  await expect(s.locator("dl").getByText("0", { exact: true })).toBeVisible();
});

test("the provenance block pins commit, tree hash, claims hash, and requested revision", async ({
  page,
}) => {
  await page.goto(`/reproduce/${MIXED}`);

  const p = provenance(page);
  await expect(p.getByText("https://github.com/example/paper-repo", { exact: true })).toBeVisible();

  // Middle-truncated hashes: the full value lives on hover (title), the
  // visible text never is the full digest.
  const commit = p.locator(`[title="${COMMIT}"]`);
  await expect(commit).toBeVisible();
  await expect(commit).not.toHaveText(COMMIT);
  const tree = p.locator(`[title="${TREE}"]`);
  await expect(tree).toBeVisible();
  await expect(tree).not.toHaveText(TREE);
  const claimsSha = p.locator(`[title="${CLAIMS_SHA}"]`);
  await expect(claimsSha).toBeVisible();

  // requested_rev lives in the unsigned manifest: labelled as invocation
  // metadata, not attested.
  await expect(
    p.getByText("requested revision (invocation metadata, not attested)", {
      exact: true,
    }),
  ).toBeVisible();
  await expect(p.getByText("v1.0", { exact: true })).toBeVisible();
});

test("the claims table renders every status literal with values and verbatim messages", async ({
  page,
}) => {
  await page.goto(`/reproduce/${MIXED}`);

  const c = claims(page);
  await expect(c.locator("tbody tr")).toHaveCount(5);
  for (const label of [
    "Reproduced",
    "Within tolerance",
    "Diverged",
    "Unverified",
    "Unknown",
  ]) {
    await expect(c.getByText(label, { exact: true })).toBeVisible();
  }

  // Claimed / observed / tolerance / delta values render per row.
  await expect(claimRow(page, "fc").getByText("0.95", { exact: true })).toHaveCount(2);
  await expect(claimRow(page, "fc").getByText("0.01", { exact: true })).toBeVisible();
  await expect(claimRow(page, "auc").getByText("0.0117", { exact: true })).toBeVisible();
  await expect(claimRow(page, "n").getByText("500", { exact: true })).toBeVisible();
  await expect(claimRow(page, "n").getByText("421", { exact: true })).toBeVisible();

  // The freshness-unverified claim renders its verbatim engine message; null
  // observed/delta render as "-", never "0" or fabricated numbers.
  const stale = claimRow(page, "stale");
  await expect(
    stale.getByText("was not rewritten by this run (mtime predates run start)"),
  ).toBeVisible();
  await expect(stale.getByText("-", { exact: true })).toHaveCount(2);
});

test("the repair history shows the env-repair step with its applied marker", async ({
  page,
}) => {
  await page.goto(`/reproduce/${MIXED}`);

  const r = repairs(page);
  // The outcome literal renders as recorded; the applied marker appears only
  // because patch_applied is true.
  await expect(r.getByText("installed_and_retried", { exact: true })).toBeVisible();
  await expect(r.getByText("Applied", { exact: true })).toBeVisible();
  await expect(r.getByText("pandas", { exact: true })).toBeVisible();
  await expect(r.getByText("installed pandas")).toBeVisible();
  await expect(r.getByText("No module named 'pandas'")).toBeVisible();
});

test("the signature card shows presence without claiming verification", async ({
  page,
}) => {
  await page.goto(`/reproduce/${MIXED}`);

  const s = signature(page);
  await expect(s.getByText("Signed bundle", { exact: true })).toBeVisible();
  await expect(s.getByText("ed25519", { exact: true })).toBeVisible();
  // Public-key fingerprint: first 8 hex chars, truncated.
  await expect(s.getByText("11111111…", { exact: true })).toBeVisible();
  // Presence is shown; nothing is claimed about the signature's validity.
  await expect(s.getByText(/valid|verified/i)).toHaveCount(0);
});

test("the download buttons trigger attachments with per-file names", async ({
  page,
}) => {
  await page.goto(`/reproduce/${MIXED}`);

  const record = page.getByRole("link", { name: "Download record" });
  const manifest = page.getByRole("link", { name: "Download manifest" });
  const sig = page.getByRole("link", { name: "Download signature" });
  await expect(record).toBeVisible();
  await expect(manifest).toBeVisible();
  await expect(sig).toBeVisible();

  await expect(record).toHaveAttribute(
    "href",
    `/api/reproduce/${MIXED}/download?file=record`,
  );
  await expect(manifest).toHaveAttribute(
    "href",
    `/api/reproduce/${MIXED}/download?file=manifest`,
  );
  await expect(sig).toHaveAttribute(
    "href",
    `/api/reproduce/${MIXED}/download?file=signature`,
  );

  const [recDownload] = await Promise.all([
    page.waitForEvent("download"),
    record.click(),
  ]);
  expect(recDownload.suggestedFilename()).toBe(`${MIXED}.reproduce_record.json`);
  const [manDownload] = await Promise.all([
    page.waitForEvent("download"),
    manifest.click(),
  ]);
  expect(manDownload.suggestedFilename()).toBe(`${MIXED}.reproduce.json`);
  const [sigDownload] = await Promise.all([
    page.waitForEvent("download"),
    sig.click(),
  ]);
  expect(sigDownload.suggestedFilename()).toBe(`${MIXED}.signature.json`);
});

test("the download route enforces its contract", async ({ page }) => {
  // record for a known bundle: 200, JSON bytes of the signed record.
  const rec = await page.request.get(
    `/api/reproduce/${MIXED}/download?file=record`,
  );
  expect(rec.status()).toBe(200);
  expect(rec.headers()["content-type"]).toContain("application/json");
  expect(await rec.json()).toMatchObject({ reproduce_id: MIXED });

  // Unknown file value: 400.
  const bogus = await page.request.get(
    `/api/reproduce/${MIXED}/download?file=bogus`,
  );
  expect(bogus.status()).toBe(400);

  // signature for a bundle without signature.json: 404.
  const noSig = await page.request.get(
    "/api/reproduce/reproduce-unverified/download?file=signature",
  );
  expect(noSig.status()).toBe(404);

  // Unknown id: 404.
  const missing = await page.request.get(
    "/api/reproduce/does-not-exist/download?file=record",
  );
  expect(missing.status()).toBe(404);
});

test("a non-zero exit reads did not complete, never a claim-status pass", async ({
  page,
}) => {
  await page.goto("/reproduce/reproduce-unverified");

  const s = summary(page);
  await expect(s.getByText("Did not complete (exit 2)", { exact: true })).toBeVisible();
  // The overall is its own presentation, NOT a claim-status badge.
  await expect(s.getByText("Unverified", { exact: true })).toHaveCount(0);

  // The single claim stays unverified with its verbatim message.
  const c = claims(page);
  await expect(c.locator("tbody tr")).toHaveCount(1);
  await expect(c.getByText("Unverified", { exact: true })).toBeVisible();
  await expect(c.getByText("run did not complete (exit 2)")).toBeVisible();
  // observed/delta are null for a run that never completed.
  await expect(claimRow(page, "x").getByText("-", { exact: true })).toHaveCount(2);
});

test("an empty bundle renders an honest unverified non-result", async ({
  page,
}) => {
  await page.goto("/reproduce/reproduce-empty");

  await expect(
    page.getByRole("heading", { name: "reproduce-empty" }),
  ).toBeVisible();
  await expect(summary(page).getByText("Unverified", { exact: true })).toBeVisible();

  // Zero claims: an honest empty row, never a fabricated pass.
  await expect(claims(page).getByText("No claims recorded.")).toBeVisible();

  // No repairs, no signature: the muted honest states, no crash.
  await expect(
    repairs(page).getByText("No repairs were needed."),
  ).toBeVisible();
  await expect(
    signature(page).getByText("Unsigned bundle", { exact: true }),
  ).toBeVisible();
  // The signature download is hidden when no signature.json exists.
  await expect(page.getByRole("link", { name: "Download signature" })).toHaveCount(0);
});

test("an unknown id returns the 404 page, not a crash", async ({ page }) => {
  const res = await page.goto("/reproduce/nope");
  expect(res?.status()).toBe(404);
});