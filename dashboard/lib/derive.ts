// Pure, client-safe derivations over a RunRecord. Kept separate from lib/runs.ts
// (which is server-only and imports fs/child_process) so client components can
// use these helpers without pulling Node modules into the browser bundle.
import type {
  AnnotationProvenance,
  QCResult,
  QCStatus,
  RunRecord,
  TaskEvent,
  Verdict,
} from "./types";

/** A task event is a failure iff its status is FAILED or its exit is non-zero.
 *  Client-safe mirror of TaskEvent.is_failure in src/contig/models.py. */
export function isTaskFailure(e: TaskEvent): boolean {
  return e.status.toUpperCase() === "FAILED" || (e.exit !== null && e.exit !== 0);
}

/** Failed/total task counts derived from a run's events (mirror of RunSummary). */
export function taskCounts(record: RunRecord): { total: number; failed: number } {
  const failed = record.events.filter(isTaskFailure).length;
  return { total: record.events.length, failed };
}

/** Did the run apply any repair? */
export function wasRepaired(record: RunRecord): boolean {
  return record.repair_history.length > 0;
}

/** Severity order for sorting/grouping (fail worst). */
export const VERDICT_ORDER: Record<Verdict, number> = {
  fail: 0,
  warn: 1,
  unverified: 2,
  pass: 3,
};

// QC severity reduction, mirror of overall_verdict in src/contig/models.py:
// a fail dominates a warn, a warn a pass. Callers handle the empty case as
// "unverified" before reaching here. "unverified" is a neutral per-check status
// (for example a concordance check with no second tool to compare against): it
// carries no severity, so it sorts last, after a clean pass, and does not drive
// the overall reduction below.
const QC_RANK: Record<QCStatus, number> = {
  fail: 0,
  warn: 1,
  pass: 2,
  unverified: 3,
};

function overallQc(results: QCResult[]): QCStatus {
  const statuses = new Set(results.map((r) => r.status));
  if (statuses.has("fail")) return "fail";
  if (statuses.has("warn")) return "warn";
  return "pass";
}

// The "lowest" deciding check is the one with the smallest numeric value (the
// nearest to breaching, e.g. the lowest mapping rate). Checks without a value
// are not eligible to be the lowest. Returns null if none carry a value.
function lowestByValue(checks: QCResult[]): QCResult | null {
  let lowest: QCResult | null = null;
  for (const c of checks) {
    if (c.value === null) continue;
    if (lowest === null || (lowest.value !== null && c.value < lowest.value)) {
      lowest = c;
    }
  }
  return lowest;
}

/**
 * The result of explaining a recorded verdict. We never re-derive trust: the
 * verdict is computed by the engine and serialized; this only names what drove
 * it (PRD contract E).
 */
export interface VerdictExplanation {
  verdict: Verdict;
  reason: string;
  decidingChecks: QCResult[];
}

/**
 * Explain a run's verdict in the same order the engine decides it
 * (src/contig/models.py RunRecord.verdict):
 *   1. any failed task event -> "fail" ("Run did not complete: N task(s) failed").
 *   2. else no qc_results    -> "unverified" ("No QC check covered this run").
 *   3. else overall = fail > warn > pass; the deciding checks are those whose
 *      status equals the overall, and the reason names the lowest one by value.
 * This presentation never changes the verdict; it only explains it.
 */
export function explainVerdict(record: RunRecord): VerdictExplanation {
  const failedTasks = record.events.filter(isTaskFailure).length;
  if (failedTasks > 0) {
    return {
      verdict: "fail",
      reason: `Run did not complete: ${failedTasks} task${
        failedTasks === 1 ? "" : "s"
      } failed`,
      decidingChecks: [],
    };
  }

  if (record.qc_results.length === 0) {
    return {
      verdict: "unverified",
      reason: "No QC check covered this run",
      decidingChecks: [],
    };
  }

  const overall = overallQc(record.qc_results);
  const decidingChecks = record.qc_results.filter((q) => q.status === overall);
  const total = record.qc_results.length;

  if (overall === "pass") {
    return {
      verdict: "pass",
      reason: `PASS: all ${total} check${total === 1 ? "" : "s"} passed`,
      decidingChecks,
    };
  }

  // fail or warn: name the count flagged and the lowest deciding check by value.
  const label = overall.toUpperCase();
  const flagged = decidingChecks.length;
  const lowest = lowestByValue(decidingChecks) ?? decidingChecks[0];
  let detail = "";
  if (lowest) {
    const range = lowest.expected_range ? ` vs ${lowest.expected_range}` : "";
    const value = lowest.value === null ? "n/a" : String(lowest.value);
    detail = ` (lowest: ${lowest.check} ${value}${range})`;
  }
  return {
    verdict: overall,
    reason: `${label}: ${flagged} of ${total} check${
      total === 1 ? "" : "s"
    } flagged${detail}`,
    decidingChecks,
  };
}

// Sort QC results so fail/warn float to the top (worst first), preserving the
// original order within a status band. Used by the QC panel and verdict card.
export function sortQcBySeverity(results: QCResult[]): QCResult[] {
  return [...results].sort((a, b) => QC_RANK[a.status] - QC_RANK[b.status]);
}

// The two concordance messages both open with an "int/int" counts token (see
// src/contig/verification/annotation_concordance.py); the FIRST such token is the
// matches/total pair. We read it rather than recompute. Mirror of the Python
// helper's _FRACTION_RE (annotation_surface.py).
const FRACTION_RE = /(\d+)\/(\d+)/;
// On the computable branch the messages open with "{label_a} vs {label_b}:";
// used only as a fallback for annotator names when annotation_identity is empty.
const LABELS_RE = /^(\S+) vs (\S+):/;

function findConcordance(
  results: QCResult[],
  check: string,
): QCResult | null {
  return (
    results.find((r) => r.kind === "concordance" && r.check === check) ?? null
  );
}

function matchesTotal(message: string): [string, string] | null {
  const m = FRACTION_RE.exec(message);
  return m ? [m[1], m[2]] : null;
}

function annotatorNames(
  identity: AnnotationProvenance[],
  consequence: QCResult,
): string {
  const tools = identity.map((p) => p.tool).filter((t): t is string => !!t);
  if (tools.length > 0) return tools.join(" and ");
  const labels = LABELS_RE.exec(consequence.message);
  if (labels) return `${labels[1]} and ${labels[2]}`;
  return "the two annotators";
}

// Render one entry as "VEP 110 (cache/build 110_GRCh38)"; the cache/build
// parenthetical is dropped when db_version is absent (no orphan label). Labeled
// "cache/build", never "database version" (PRD D1). Mirror of _annotation_clause
// in src/contig/methods.py.
function formatAnnotator(ai: AnnotationProvenance): string {
  const base = ai.version ? `${ai.tool} ${ai.version}` : ai.tool;
  return ai.db_version ? `${base} (cache/build ${ai.db_version})` : base;
}

// The annotation identity as one "; "-joined note (e.g.
// "VEP 110 (cache/build 110_GRCh38); SnpEff 5.1 (cache/build GRCh38.105)"), or
// null when no annotation provenance was recorded.
export function annotationIdentityNote(
  identity: AnnotationProvenance[] | undefined,
): string | null {
  if (!identity || identity.length === 0) return null;
  return identity.map(formatAnnotator).join("; ");
}

/**
 * Render M4's cross-tool concordance results as one plain-language
 * "Corroborated by ..." line, or null. Client-safe mirror of
 * corroborated_by_line in src/contig/verification/annotation_surface.py: it READS
 * the already-computed consequence_concordance / gene_symbol_concordance QC
 * results plus annotation_identity and never recomputes. Returns null when the
 * consequence check is missing or its value is null (PRD D2), so a fabricated
 * agreement number is never shown. The gene-symbol clause is marked
 * "informational" (PRD D3 / S-1) so a low fraction never reads as a failure.
 */
export function corroboratedByLine(
  record: Pick<RunRecord, "qc_results" | "annotation_identity">,
): string | null {
  const consequence = findConcordance(record.qc_results, "consequence_concordance");
  if (!consequence || consequence.value === null) return null;

  const consCounts = matchesTotal(consequence.message);
  if (!consCounts) return null; // defensive: computable branch always has counts
  const [consMatches, consTotal] = consCounts;

  const names = annotatorNames(record.annotation_identity ?? [], consequence);
  let line = `Corroborated by ${names}: ${consMatches}/${consTotal} consequences agree (${consequence.value.toFixed(2)})`;

  const geneSymbol = findConcordance(record.qc_results, "gene_symbol_concordance");
  if (geneSymbol && geneSymbol.value !== null) {
    const gsCounts = matchesTotal(geneSymbol.message);
    if (gsCounts) {
      const [gsMatches, gsTotal] = gsCounts;
      line += `; gene symbols ${gsMatches}/${gsTotal} (${geneSymbol.value.toFixed(2)}, informational)`;
    }
  }

  return line + ".";
}

// The detector's failure classes (mirror of FailureClass in src/contig/models.py).
// Used by the curation UI to correct a provisional label, and to validate input.
export const FAILURE_CLASSES = [
  "oom",
  "time_limit",
  "missing_reference",
  "missing_index",
  "bad_param",
  "container_pull_failed",
  "container_unavailable",
  "conda_solve_failed",
  "platform_unsupported",
  "tool_crash",
  "no_progress",
  "qc_anomaly",
  "unknown",
] as const;
