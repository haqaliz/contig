// QC results: a full table plus a per-sample drill-down so a researcher can see
// *which sample* failed, not just that something did. QC check names follow the
// convention "<check>:<sample>" for per-sample checks (e.g. "alignment_rate:WT_REP1")
// and a set of cross-sample checks ("min_sample_count", "library_size_skew:total_reads",
// "outlier:<metric>:<sample>"). We parse those keys into groups here. The verdict
// itself comes from the engine, this panel only surfaces the underlying checks.
import { StatusBadge } from "@/components/status-badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  annotationIdentityNote,
  corroboratedByLine,
} from "@/lib/derive";
import type { AnnotationProvenance, QCResult, QCStatus } from "@/lib/types";

// Cross-sample checks are run across the whole batch, not per-sample. Their keys
// either have no sample suffix ("min_sample_count") or describe a batch metric.
const CROSS_SAMPLE_PREFIXES = [
  "min_sample_count",
  "library_size_skew",
  "outlier",
];

function isCrossSample(check: string): boolean {
  return CROSS_SAMPLE_PREFIXES.some(
    (p) => check === p || check.startsWith(`${p}:`),
  );
}

// Parse "<check>:<sample>" into its parts. Two shapes exist:
//   "alignment_rate:WT_REP1"          -> first colon splits check from sample
//   "outlier:total_reads:WT_REP1"     -> two colons: outlier:<metric>:<sample>
// For the outlier form the sample is everything after the LAST colon and the
// "check" keeps its metric. Anything with no colon is a whole-check key with no
// sample (e.g. "min_sample_count").
function parseCheck(check: string): { check: string; sample: string | null } {
  if (check.startsWith("outlier:")) {
    const last = check.lastIndexOf(":");
    return { check: check.slice(0, last), sample: check.slice(last + 1) };
  }
  const first = check.indexOf(":");
  if (first === -1) return { check, sample: null };
  return { check: check.slice(0, first), sample: check.slice(first + 1) };
}

// Severity order so a sample's worst status floats to the top of its group.
// "unverified" is neutral (no severity), so it sorts last, after a clean pass.
const STATUS_RANK: Record<QCStatus, number> = {
  fail: 0,
  warn: 1,
  pass: 2,
  unverified: 3,
};

function worst(a: QCStatus, b: QCStatus): QCStatus {
  return STATUS_RANK[a] <= STATUS_RANK[b] ? a : b;
}

function formatValue(value: number | null): string {
  if (value === null) return "n/a";
  // Large integer-ish counts read better without decimals.
  if (Number.isInteger(value)) return value.toLocaleString("en-US");
  return value.toLocaleString("en-US", { maximumFractionDigits: 4 });
}

function QcRows({ rows }: { rows: QCResult[] }) {
  // Fail/warn checks float to the top so a reviewer sees the flagged ones first;
  // ties keep their original order (a stable sort by status rank).
  const sorted = [...rows].sort(
    (a, b) => STATUS_RANK[a.status] - STATUS_RANK[b.status],
  );
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead scope="col">Check</TableHead>
          <TableHead scope="col">Status</TableHead>
          <TableHead scope="col" className="text-right">
            Value
          </TableHead>
          <TableHead scope="col">Expected range</TableHead>
          <TableHead scope="col">Message</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {sorted.map((q) => (
          <TableRow key={q.check}>
            <TableCell className="font-mono text-xs whitespace-normal">
              {q.check}
            </TableCell>
            <TableCell>
              <StatusBadge status={q.status} />
            </TableCell>
            <TableCell className="text-right font-mono text-xs">
              {formatValue(q.value)}
            </TableCell>
            <TableCell className="font-mono text-xs">
              {q.expected_range ?? "n/a"}
            </TableCell>
            <TableCell className="whitespace-normal text-muted-foreground">
              {q.message}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

export function QcPanel({
  qcResults,
  annotationIdentity,
}: {
  qcResults: QCResult[];
  annotationIdentity?: AnnotationProvenance[];
}) {
  if (qcResults.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Quality control</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            No QC checks ran (this run is unverified).
          </p>
        </CardContent>
      </Card>
    );
  }

  // Structural and integrity checks (PRD contract C) verify the output files
  // themselves (present, non-empty, valid), not a content metric. They carry
  // kind "structural", so we pull them into their own section and leave the
  // metric checks to the existing per-sample and cross-sample grouping.
  const structural = qcResults.filter((q) => q.kind === "structural");
  // Concordance checks corroborate a result across tools (cross-tool agreement).
  // They carry kind "concordance" and get their own section, mirroring structural.
  // A check with no second tool to compare against reports status "unverified".
  const concordance = qcResults.filter((q) => q.kind === "concordance");
  // The plain-language "Corroborated by ..." line, read (never recomputed) from
  // the concordance results + annotation identity. Null when there is no
  // computable consequence concordance (PRD D2), in which case no line is shown.
  const corroboration = corroboratedByLine({
    qc_results: qcResults,
    annotation_identity: annotationIdentity,
  });
  // The annotation tool(s) + cache/build id, surfaced honestly (PRD D1).
  const identityNote = annotationIdentityNote(annotationIdentity);
  const metric = qcResults.filter(
    (q) => q.kind !== "structural" && q.kind !== "concordance",
  );
  const cross = metric.filter((q) => isCrossSample(q.check));
  const perSample = metric.filter((q) => !isCrossSample(q.check));

  // Group per-sample checks by the sample parsed from their key. Checks whose
  // key carries no sample fall into a shared "(no sample)" bucket.
  const groups = new Map<string, { status: QCStatus; rows: QCResult[] }>();
  for (const q of perSample) {
    const { sample } = parseCheck(q.check);
    const key = sample ?? "(no sample)";
    const existing = groups.get(key);
    if (existing) {
      existing.rows.push(q);
      existing.status = worst(existing.status, q.status);
    } else {
      groups.set(key, { status: q.status, rows: [q] });
    }
  }
  const sampleGroups = [...groups.entries()].sort(
    ([, a], [, b]) =>
      STATUS_RANK[a.status] - STATUS_RANK[b.status] ||
      b.rows.length - a.rows.length,
  );

  return (
    <div className="space-y-6">
      {structural.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Structural and integrity checks</CardTitle>
            <CardDescription>
              Checks on the output files themselves: that the expected outputs are
              present, non-empty, and not corrupt. A missing or empty required
              output fails the verdict.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <QcRows rows={structural} />
          </CardContent>
        </Card>
      )}

      {concordance.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Concordance (cross-tool corroboration)</CardTitle>
            <CardDescription>
              Checks that corroborate a result by comparing it across independent
              tools. Agreement raises confidence in the output. A check with no
              second tool to compare against is reported as unverified (a neutral
              state, not a failure).
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {corroboration && (
              <p className="text-sm text-foreground">{corroboration}</p>
            )}
            {identityNote && (
              <p className="text-xs text-muted-foreground">
                Annotation: {identityNote} (research use).
              </p>
            )}
            <QcRows rows={concordance} />
          </CardContent>
        </Card>
      )}

      {sampleGroups.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Per-sample checks</CardTitle>
            <CardDescription>
              Grouped by sample so you can see which one failed. Each group is
              tagged with its worst status.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            {sampleGroups.map(([sample, group]) => (
              <section key={sample} aria-label={`Sample ${sample}`}>
                <h3 className="mb-2 flex items-center gap-2 text-sm font-medium">
                  <StatusBadge status={group.status} />
                  <span className="font-mono">{sample}</span>
                  <span className="text-xs text-muted-foreground">
                    ({group.rows.length}{" "}
                    {group.rows.length === 1 ? "check" : "checks"})
                  </span>
                </h3>
                <QcRows rows={group.rows} />
              </section>
            ))}
          </CardContent>
        </Card>
      )}

      {cross.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Cross-sample checks</CardTitle>
            <CardDescription>
              Batch-level checks that compare samples to each other
              (min_sample_count, library_size_skew, outlier).
            </CardDescription>
          </CardHeader>
          <CardContent>
            <QcRows rows={cross} />
          </CardContent>
        </Card>
      )}
    </div>
  );
}
