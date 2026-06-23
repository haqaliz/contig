import { test, expect } from "@playwright/test";

import { canViewRun, filterOwnedRunIds, type Viewer } from "../lib/ownership";
import type { RunOwner } from "../lib/types";

// Unit-level coverage of the per-user isolation rule (PRD contract E). These run
// in Node (no `page`), exercising the pure rule from lib/ownership.ts directly, so
// the denial logic is verified without a live tenant or a browser. The e2e
// ownership spec then confirms the bypass (admin sees all) end to end.

const alice: Viewer = { owner: "auth0|alice", isAdmin: false };
const admin: Viewer = { owner: "auth0|admin", isAdmin: true };

const ownedByAlice: RunOwner = { owner: "auth0|alice", email: "alice@example.com" };
const ownedByBob: RunOwner = { owner: "auth0|bob", email: "bob@example.com" };

test("a user sees only the runs they own", () => {
  expect(canViewRun(alice, ownedByAlice)).toBe(true);
  expect(canViewRun(alice, ownedByBob)).toBe(false);
});

test("an untagged run is admin-only", () => {
  // A run with no owner.json (e.g. a CLI launch) is hidden from a regular user.
  expect(canViewRun(alice, null)).toBe(false);
  // An admin still sees it.
  expect(canViewRun(admin, null)).toBe(true);
});

test("an admin sees every run regardless of owner", () => {
  expect(canViewRun(admin, ownedByAlice)).toBe(true);
  expect(canViewRun(admin, ownedByBob)).toBe(true);
});

test("filterOwnedRunIds returns only the visible ids for a user", () => {
  const runs = [
    { id: "run-a", owner: ownedByAlice },
    { id: "run-b", owner: ownedByBob },
    { id: "run-c", owner: null },
  ];
  // Alice sees only her own run; Bob's and the untagged one are filtered out.
  expect(filterOwnedRunIds(alice, runs)).toEqual(["run-a"]);
  // The admin sees all three, in order.
  expect(filterOwnedRunIds(admin, runs)).toEqual(["run-a", "run-b", "run-c"]);
});
