// The self-heal outcome-match trend (C6 self-heal regression guard). It plots
// the self-heal loop's outcome-match rate against a frozen scenario corpus over
// time as an inline SVG sparkline, and lists each snapshot in a table with the
// outcome-match delta and the recovery count against the previous snapshot.
// Server Component: it receives the already-loaded history and renders. Empty
// history degrades to a short note.
import {
  Card,
  CardContent,
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
import type { HealSnapshot } from "@/lib/types";
import { DeltaCell, Sparkline, pct } from "@/components/eval/trend-primitives";

// Every class seen across the two snapshots being compared, sorted, so a class
// that appeared or vanished still shows a row.
function classKeys(curr: HealSnapshot, prev: HealSnapshot | null): string[] {
  const keys = new Set<string>(Object.keys(curr.per_class));
  if (prev) for (const k of Object.keys(prev.per_class)) keys.add(k);
  return [...keys].sort((a, b) => a.localeCompare(b));
}

export function HealHistory({ history }: { history: HealSnapshot[] }) {
  if (history.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
            Self-heal outcome-match over time
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            No self-heal snapshots have been recorded yet. Each{" "}
            <code className="font-mono">contig heal-guard --snapshot</code>{" "}
            appends one, scoring the self-heal loop against the frozen
            scenario corpus, and the trend appears here.
          </p>
        </CardContent>
      </Card>
    );
  }

  // Newest first for the table; the latest snapshot is compared to the one before
  // it. The sparkline keeps file (chronological) order so time reads left to right.
  const newestFirst = [...history].reverse();
  const latest = newestFirst[0];
  const previous = newestFirst.length > 1 ? newestFirst[1] : null;

  return (
    <section className="flex flex-col gap-4" aria-labelledby="heal-trend-heading">
      <h2 id="heal-trend-heading" className="font-heading text-lg font-medium">
        Self-heal outcome-match over time
      </h2>

      <Card>
        <CardContent className="space-y-4 pt-6">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <span className="text-xs text-muted-foreground">
              {history.length} snapshot{history.length === 1 ? "" : "s"}
            </span>
            <span className="font-mono text-sm tabular-nums">
              latest {pct(latest.outcome_match_rate)}
            </span>
          </div>
          <Sparkline
            values={history.map((s) => s.outcome_match_rate)}
            ariaLabel="Self-heal outcome-match over time"
          />
          <div className="flex justify-between text-xs text-muted-foreground tabular-nums">
            <span>{new Date(history[0].timestamp).toLocaleDateString()}</span>
            <span>
              {new Date(history[history.length - 1].timestamp).toLocaleDateString()}
            </span>
          </div>
        </CardContent>
      </Card>

      {/* Snapshot table: each row is a snapshot, newest first, with the
          outcome-match delta against the previous one and the recovery count. */}
      <Card>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead scope="col">When</TableHead>
                <TableHead scope="col" className="text-right">
                  Scenarios
                </TableHead>
                <TableHead scope="col" className="text-right">
                  Outcome-match
                </TableHead>
                <TableHead scope="col" className="text-right">
                  Delta
                </TableHead>
                <TableHead scope="col" className="text-right">
                  Recovery
                </TableHead>
                <TableHead scope="col">Version</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {newestFirst.map((snap, i) => {
                const prev = newestFirst[i + 1] ?? null;
                return (
                  <TableRow key={`${snap.timestamp}-${i}`}>
                    <TableCell className="whitespace-nowrap tabular-nums">
                      {new Date(snap.timestamp).toLocaleString()}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {snap.scenario_count}
                    </TableCell>
                    <TableCell className="text-right font-medium tabular-nums">
                      {pct(snap.outcome_match_rate)}
                    </TableCell>
                    <TableCell className="text-right">
                      <DeltaCell
                        curr={snap.outcome_match_rate}
                        prev={prev ? prev.outcome_match_rate : null}
                      />
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {Math.round(snap.recovery_rate * snap.scenario_count)}/
                      {snap.scenario_count}
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

      {/* Per-class outcome-match rate deltas, latest vs the previous snapshot. */}
      <section className="flex flex-col gap-3" aria-labelledby="heal-class-delta-heading">
        <h3
          id="heal-class-delta-heading"
          className="font-heading text-base font-medium"
        >
          Self-heal per-class change, latest snapshot
        </h3>
        <Card>
          <CardContent>
            {previous === null ? (
              <p className="text-sm text-muted-foreground">
                Only one snapshot so far, so there is nothing to compare against
                yet. The next snapshot will show per-class movement here.
              </p>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead scope="col">Class</TableHead>
                    <TableHead scope="col" className="text-right">
                      Matched
                    </TableHead>
                    <TableHead scope="col" className="text-right">
                      Rate
                    </TableHead>
                    <TableHead scope="col" className="text-right">
                      Rate delta
                    </TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {classKeys(latest, previous).map((name) => {
                    const curr = latest.per_class[name];
                    const prev = previous.per_class[name];
                    return (
                      <TableRow key={name}>
                        <TableHead scope="row" className="font-mono font-medium">
                          {name}
                        </TableHead>
                        <TableCell className="text-right tabular-nums">
                          {curr ? `${curr.matched}/${curr.total}` : "n/a"}
                        </TableCell>
                        <TableCell className="text-right tabular-nums">
                          {curr ? pct(curr.rate) : "n/a"}
                        </TableCell>
                        <TableCell className="text-right">
                          {curr && prev ? (
                            <DeltaCell curr={curr.rate} prev={prev.rate} />
                          ) : (
                            <span className="text-muted-foreground">
                              {curr ? "new" : "gone"}
                            </span>
                          )}
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>
      </section>
    </section>
  );
}
