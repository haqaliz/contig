// The pure per-user run isolation rule (PRD contract E), with no disk or server
// dependency, so it can be unit-tested in isolation (lib/runs.ts carries a
// "server-only" guard that throws outside a server context; this module does not,
// so the rule is importable from a plain test). lib/runs.ts re-exports these and
// applies them over the runs directory.
import type { RunOwner } from "./types";

/** The viewer an ownership rule is applied for: their identity and admin flag. */
export interface Viewer {
  owner: string;
  isAdmin: boolean;
}

/**
 * Whether a viewer may see a run with the given owner tag. An admin sees every
 * run. A regular user sees only runs they own; a run with no owner tag (null,
 * e.g. a CLI launch) is admin-only.
 */
export function canViewRun(viewer: Viewer, owner: RunOwner | null): boolean {
  if (viewer.isAdmin) return true;
  if (!owner) return false;
  return owner.owner === viewer.owner;
}

/**
 * Filter (run id, owner tag) pairs to those a viewer may see, returning the
 * visible ids: an admin sees all, a user sees only their own, an untagged run is
 * admin-only.
 */
export function filterOwnedRunIds(
  viewer: Viewer,
  runs: { id: string; owner: RunOwner | null }[],
): string[] {
  return runs.filter((r) => canViewRun(viewer, r.owner)).map((r) => r.id);
}
