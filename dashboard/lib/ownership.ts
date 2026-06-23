// The pure per-user run isolation rule (PRD contract E), with no disk or server
// dependency, so it can be unit-tested in isolation (lib/runs.ts carries a
// "server-only" guard that throws outside a server context; this module does not,
// so the rule is importable from a plain test). lib/runs.ts re-exports these and
// applies them over the runs directory.
import type { RunOwner } from "./types";

// The viewer an ownership rule is applied for: their identity, admin flag, and
// the shared workspaces they belong to. workspaces drives shared visibility (PRD
// section A): a viewer also sees any run tagged with a workspace they are in.
export interface Viewer {
  owner: string;
  isAdmin: boolean;
  workspaces: string[];
}

/**
 * Whether a viewer may see a run with the given owner tag. An admin sees every
 * run. A regular user sees runs they own, plus any run tagged with a workspace
 * they belong to (PRD section A); a run with no owner tag (null, e.g. a CLI
 * launch) is admin-only. The solo case (a run with no workspace) is unchanged:
 * only its owner (or an admin) sees it.
 */
export function canViewRun(viewer: Viewer, owner: RunOwner | null): boolean {
  if (viewer.isAdmin) return true;
  if (!owner) return false;
  if (owner.owner === viewer.owner) return true;
  return (
    owner.workspace !== undefined && viewer.workspaces.includes(owner.workspace)
  );
}

/**
 * Filter (run id, owner tag) pairs to those a viewer may see, returning the
 * visible ids: an admin sees all, a user sees their own plus their workspaces'
 * shared runs, an untagged run is admin-only.
 */
export function filterOwnedRunIds(
  viewer: Viewer,
  runs: { id: string; owner: RunOwner | null }[],
): string[] {
  return runs.filter((r) => canViewRun(viewer, r.owner)).map((r) => r.id);
}
