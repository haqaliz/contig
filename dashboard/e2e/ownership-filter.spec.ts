import { test, expect } from "@playwright/test";

import { canViewRun, filterOwnedRunIds, type Viewer } from "../lib/ownership";
import type { RunOwner } from "../lib/types";

// Unit-level coverage of the per-user isolation rule (PRD contract E) and shared
// workspace visibility (PRD section A). These run in Node (no `page`), exercising
// the pure rule from lib/ownership.ts directly, so the denial logic is verified
// without a live tenant or a browser. The e2e ownership spec then confirms the
// bypass (admin sees all) end to end.

// Alice is in the "lab-x" workspace; Bob is solo (no workspace). The admin sees
// everything regardless of ownership or workspace.
const alice: Viewer = {
  owner: "auth0|alice",
  isAdmin: false,
  workspaces: ["lab-x"],
};
const bob: Viewer = { owner: "auth0|bob", isAdmin: false, workspaces: [] };
const admin: Viewer = { owner: "auth0|admin", isAdmin: true, workspaces: [] };

const ownedByAlice: RunOwner = { owner: "auth0|alice", email: "alice@example.com" };
const ownedByBob: RunOwner = { owner: "auth0|bob", email: "bob@example.com" };
// A run Bob owns but shared into the "lab-x" workspace: Alice (a member) sees it.
const sharedInLabX: RunOwner = {
  owner: "auth0|bob",
  email: "bob@example.com",
  workspace: "lab-x",
};
// A run shared into a workspace Alice is not in: she does not see it.
const sharedInLabY: RunOwner = {
  owner: "auth0|carol",
  email: "carol@example.com",
  workspace: "lab-y",
};

test("a user sees only the runs they own", () => {
  expect(canViewRun(alice, ownedByAlice)).toBe(true);
  expect(canViewRun(alice, ownedByBob)).toBe(false);
});

test("a user sees a run shared into a workspace they belong to", () => {
  // Alice is in lab-x, so she sees Bob's run shared into lab-x even though she
  // does not own it.
  expect(canViewRun(alice, sharedInLabX)).toBe(true);
});

test("a user does not see a run shared into a workspace they are not in", () => {
  // The run is shared into lab-y; Alice is only in lab-x, so it stays hidden.
  expect(canViewRun(alice, sharedInLabY)).toBe(false);
});

test("a solo user does not gain workspace-shared runs", () => {
  // Bob is in no workspace, so a workspace-shared run he does not own is hidden;
  // the solo (no-workspace) case is unchanged.
  expect(canViewRun(bob, sharedInLabX)).toBe(true); // he owns this one
  expect(canViewRun(bob, sharedInLabY)).toBe(false);
});

test("an untagged run is admin-only", () => {
  // A run with no owner.json (e.g. a CLI launch) is hidden from a regular user.
  expect(canViewRun(alice, null)).toBe(false);
  // An admin still sees it.
  expect(canViewRun(admin, null)).toBe(true);
});

test("an admin sees every run regardless of owner or workspace", () => {
  expect(canViewRun(admin, ownedByAlice)).toBe(true);
  expect(canViewRun(admin, ownedByBob)).toBe(true);
  expect(canViewRun(admin, sharedInLabY)).toBe(true);
});

test("filterOwnedRunIds returns only the visible ids for a user", () => {
  const runs = [
    { id: "run-a", owner: ownedByAlice },
    { id: "run-b", owner: ownedByBob },
    { id: "run-c", owner: null },
    { id: "run-d", owner: sharedInLabX },
    { id: "run-e", owner: sharedInLabY },
  ];
  // Alice sees her own run and the lab-x shared run; Bob's solo run, the untagged
  // one, and the lab-y shared run are filtered out.
  expect(filterOwnedRunIds(alice, runs)).toEqual(["run-a", "run-d"]);
  // The admin sees all five, in order.
  expect(filterOwnedRunIds(admin, runs)).toEqual([
    "run-a",
    "run-b",
    "run-c",
    "run-d",
    "run-e",
  ]);
});
