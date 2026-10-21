// Summary card for the /reproduce index (C8). Reads only the records the page
// already loaded and derives the same worst-of overall the table shows, so there
// is no extra API route and no second disk read. Renders nothing when there are
// no reproductions.
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ReproduceStatusBadge } from "@/components/reproduce-status-badge";
import { reproduceSummary } from "@/lib/reproduce-derive";
import type { ReproduceRecord } from "@/lib/types";

// Worst first, so the status a reader should look at leads the counts.
const OVERALL_ORDER = [
  "did_not_complete",
  "diverged",
  "within_tolerance",
  "unverified",
  "reproduced",
];

export function ReproduceSummary({ records }: { records: ReproduceRecord[] }) {
  if (records.length === 0) return null;
  const summary = reproduceSummary(records);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
          {summary.total} reproduction{summary.total === 1 ? "" : "s"} by verdict
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <ul className="flex flex-wrap gap-x-5 gap-y-2">
          {OVERALL_ORDER.filter((status) => (summary.byOverall[status] ?? 0) > 0).map(
            (status) => (
              <li key={status} className="flex items-center gap-2">
                <ReproduceStatusBadge status={status} />
                <span className="font-mono text-sm tabular-nums">
                  {summary.byOverall[status]}
                </span>
              </li>
            ),
          )}
        </ul>

        <div>
          <h3 className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
            Recent verdicts
          </h3>
          <ul className="mt-2 space-y-1.5">
            {summary.recent.map((recent) => (
              <li key={recent.id} className="flex flex-wrap items-center gap-2 text-sm">
                <span className="font-mono">{recent.id}</span>
                <ReproduceStatusBadge status={recent.overall} />
                <span className="text-xs text-muted-foreground tabular-nums">
                  {new Date(recent.createdAt).toLocaleDateString()}
                </span>
              </li>
            ))}
          </ul>
        </div>
      </CardContent>
    </Card>
  );
}
