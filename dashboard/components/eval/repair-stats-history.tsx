// The repair-stats unattended-completion trend (C2-14). Unlike the guard
// trends this reads REAL run bundles, so every point depends on whichever runs
// directory was scanned and is not reproducible from committed data. The card
// plots the rate over time and states that caveat; a snapshot with nothing
// scorable is shown as "not computable" and left out of the sparkline rather
// than plotted as 0%. Server Component: it receives the already-loaded history.
import { Card, CardContent } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { RepairStatsSnapshot } from "@/lib/types";
import {
  repairStatsRateLabel,
  repairStatsRateSeries,
} from "@/lib/derive";
import { DeltaCell, Sparkline } from "@/components/eval/trend-primitives";

export function RepairStatsHistory({ history }: { history: RepairStatsSnapshot[] }) {
  if (history.length === 0) return null;

  // Newest first for the table; the latest snapshot is compared to the one
  // before it. The sparkline keeps file (chronological) order.
  const newestFirst = [...history].reverse();
  const latest = newestFirst[0];
  const series = repairStatsRateSeries(history);

  return (
    <section
      className="flex flex-col gap-4"
      aria-labelledby="repair-stats-trend-heading"
    >
      <h2
        id="repair-stats-trend-heading"
        className="font-heading text-lg font-medium"
      >
        Repair-stats unattended completion over time
      </h2>

      <Card>
        <CardContent className="space-y-4 pt-6">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <span className="text-xs text-muted-foreground">
              {history.length} snapshot{history.length === 1 ? "" : "s"} over real
              run bundles
            </span>
            <span className="font-mono text-sm tabular-nums">
              latest {repairStatsRateLabel(latest.unattended_completion_rate)}
            </span>
          </div>
          {series.length > 0 ? (
            <>
              <Sparkline
                values={series}
                ariaLabel="Repair-stats unattended completion over time"
              />
              <div className="flex justify-between text-xs text-muted-foreground tabular-nums">
                <span>{new Date(history[0].timestamp).toLocaleDateString()}</span>
                <span>
                  {new Date(history[history.length - 1].timestamp).toLocaleDateString()}
                </span>
              </div>
            </>
          ) : (
            <p className="text-sm text-muted-foreground">
              No recorded snapshot had a computable rate yet.
            </p>
          )}
          <p className="text-xs text-muted-foreground">
            A completion rate, not a recovery rate: it mostly counts runs that
            never failed, and each point scans whatever runs directory
            <code className="font-mono"> repair-stats --snapshot</code> was
            pointed at.
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead scope="col">When</TableHead>
                <TableHead scope="col" className="text-right">
                  Runs
                </TableHead>
                <TableHead scope="col" className="text-right">
                  Steps
                </TableHead>
                <TableHead scope="col" className="text-right">
                  Completion
                </TableHead>
                <TableHead scope="col" className="text-right">
                  Delta
                </TableHead>
                <TableHead scope="col">Version</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {newestFirst.map((snap, i) => {
                const prev = newestFirst[i + 1] ?? null;
                const curr = snap.unattended_completion_rate;
                const prevRate = prev ? prev.unattended_completion_rate : null;
                return (
                  <TableRow key={`${snap.timestamp}-${i}`}>
                    <TableCell className="whitespace-nowrap tabular-nums">
                      {new Date(snap.timestamp).toLocaleString()}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {snap.runs_total}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {snap.steps_total}
                    </TableCell>
                    <TableCell className="text-right font-medium tabular-nums">
                      {repairStatsRateLabel(curr)}
                      <span className="ml-1 text-xs font-normal text-muted-foreground">
                        {curr === null
                          ? ""
                          : `(${snap.unattended_completed}/${snap.rate_denominator})`}
                      </span>
                    </TableCell>
                    <TableCell className="text-right">
                      {curr !== null && prevRate !== null ? (
                        <DeltaCell curr={curr} prev={prevRate} />
                      ) : (
                        <span className="text-muted-foreground">—</span>
                      )}
                    </TableCell>
                    <TableCell className="font-mono text-xs text-muted-foreground">
                      {snap.contig_version ?? "unknown"}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </section>
  );
}
