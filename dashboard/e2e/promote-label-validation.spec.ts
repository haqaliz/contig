import { test, expect } from "@playwright/test";

// The relabel round-trip for a failure class that used to be missing from the
// dashboard's FAILURE_CLASSES list (the list itself is pinned by
// failure-classes.spec.ts). The promote route validates a corrective label
// against that list, so a class that is not in it is rejected with a 400
// "Unknown failure class." and a human could never fix the provisional label.
// We POST a label for a case id that is format-valid but does not exist in the
// pending corpus: the request must clear validation and reach the promote step
// (the CLI then fails, which the route reports as its "Could not promote the
// case" 500) — proving the label itself passed the gate. Nothing is written to
// the golden corpus.

test("promote route accepts a previously-missing failure class label", async ({
  request,
}) => {
  const res = await request.post("/api/corpus/promote", {
    data: { case_id: "no-such-case-zzz-2026", label: "disk_full" },
  });
  expect(res.status()).toBe(500);
  const body = (await res.json()) as { error?: string };
  expect(body.error).toMatch(/Could not promote the case/);
});

test("promote route accepts the reference_mismatch failure class label", async ({
  request,
}) => {
  const res = await request.post("/api/corpus/promote", {
    data: { case_id: "no-such-case-zzz-2026", label: "reference_mismatch" },
  });
  expect(res.status()).toBe(500);
  const body = (await res.json()) as { error?: string };
  expect(body.error).toMatch(/Could not promote the case/);
});
