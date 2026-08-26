// Pure, client-safe derivations over a ReproduceRecord (the third-party `contig
// reproduce` track, C8). Kept free of "server-only" (the lib/ownership.ts
// precedent) so the worst-of rule, labels, and counts line are unit-observable;
// lib/reproduce.ts carries the server-only guard and does the disk reads.
//
// There is no overall verdict on the record -- only per-claim statuses plus
// exit_code -- so this derives one, worst-of, mirroring the runs-table
// convention (fail > warn > unverified > pass): diverged > within_tolerance >
// unverified > reproduced. An unknown status literal counts as unverified
// (honest, never a pass); a non-zero exit_code reads as its own
// "did_not_complete" presentation, never as a claim-status badge.
import type { ReproduceClaim, ReproduceRecord, ReproduceStatus } from "./types";

// The derived overall for a record: the worst claim status, or
// "did_not_complete" when exit_code !== 0.
export type ReproduceOverall = ReproduceStatus | "did_not_complete";

// Severity order for sorting/grouping (diverged worst). Unknown literals
// resolve to the `unverified` rank (never crash, never a pass).
export const REPRODUCE_STATUS_ORDER: Record<string, number> = {
  diverged: 0,
  within_tolerance: 1,
  unverified: 2,
  reproduced: 3,
};

function statusRank(status: string): number {
  return REPRODUCE_STATUS_ORDER[status] ?? REPRODUCE_STATUS_ORDER.unverified;
}

// The canonical status for a severity rank (inverse of REPRODUCE_STATUS_ORDER).
// Used so an unknown literal resolves to "unverified" for the OVERALL while its
// count is still tallied under its own literal key.
function statusForRank(rank: number): ReproduceStatus {
  for (const [status, r] of Object.entries(REPRODUCE_STATUS_ORDER)) {
    if (r === rank) return status as ReproduceStatus;
  }
  return "unverified";
}

function tally(claims: ReproduceClaim[]): Record<string, number> {
  const counts: Record<string, number> = {};
  for (const claim of claims) {
    counts[claim.status] = (counts[claim.status] ?? 0) + 1;
  }
  return counts;
}

/**
 * The derived overall status for a reproduce record and the per-status claim
 * tally. A non-zero exit_code short-circuits to "did_not_complete" (the claims
 * still read as they were recorded -- for a non-completed run the engine writes
 * them unverified -- so counts are still tallied). Otherwise it is the worst-of
 * over the claim statuses; an empty claim_results is an honest "unverified"
 * non-result, never a pass. Unknown literals are counted under their literal
 * key and rank as unverified for the overall.
 */
export function deriveReproduceOverall(
  record: Pick<ReproduceRecord, "exit_code" | "claim_results">,
): { overall: ReproduceOverall; counts: Record<string, number> } {
  const counts = tally(record.claim_results);
  if (record.exit_code !== 0) {
    return { overall: "did_not_complete", counts };
  }
  if (record.claim_results.length === 0) {
    return { overall: "unverified", counts };
  }
  let worstRank = REPRODUCE_STATUS_ORDER.reproduced;
  for (const claim of record.claim_results) {
    worstRank = Math.min(worstRank, statusRank(claim.status));
  }
  return { overall: statusForRank(worstRank), counts };
}

/** Human label for a claim-status literal; anything unknown reads "Unknown". */
export function claimStatusLabel(status: string): string {
  switch (status) {
    case "reproduced":
      return "Reproduced";
    case "within_tolerance":
      return "Within tolerance";
    case "diverged":
      return "Diverged";
    case "unverified":
      return "Unverified";
    default:
      return "Unknown";
  }
}

// The known literals in display order for the counts line (reproduced first,
// mirroring the "2 reproduced · 1 diverged · 1 unverified" presentation).
const COUNTS_ORDER = ["reproduced", "within_tolerance", "diverged", "unverified"];

/**
 * The per-status claim counts as one line, e.g. "1 reproduced · 1 within
 * tolerance · 1 diverged · 1 unverified · 1 suspicious". Unknown literals are
 * counted under their own key (sorted after the known ones), never dropped or
 * mislabeled. A record with no claims reads "No claims" -- an honest
 * non-result, never "0 reproduced".
 */
export function claimCountsLine(counts: Record<string, number>): string {
  const keys = [
    ...COUNTS_ORDER.filter((k) => (counts[k] ?? 0) > 0),
    ...Object.keys(counts)
      .filter((k) => !COUNTS_ORDER.includes(k))
      .sort(),
  ];
  if (keys.length === 0) return "No claims";
  return keys
    .map((k) => `${counts[k]} ${k.replaceAll("_", " ")}`)
    .join(" · ");
}