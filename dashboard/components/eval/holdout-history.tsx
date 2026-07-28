// The held-out-accuracy trend (C6 self-heal regression guard). It plots the
// detector's accuracy against the FROZEN held-out corpus over time as an inline
// SVG sparkline and lists each snapshot in a table with per-class precision and
// recall deltas against the previous snapshot. This is distinct from
// EvalHistory (which trends accuracy on the training/growing corpus): the
// held-out set never grows, so a drift here is a real regression signal, not
// noise from new coverage. Server Component: it receives the already-loaded
// history and renders. Empty history degrades to a short note.
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
import type { EvalSnapshot } from "@/lib/types";
import { DeltaCell, Sparkline, pct } from "@/components/eval/trend-primitives";

// Every class seen across the two snapshots being compared, sorted, so a class
// that appeared or vanished still shows a row.
function classKeys(curr: EvalSnapshot, prev: EvalSnapshot | null): string[] {
  const keys = new Set<string>(Object.keys(curr.per_class));
  if (prev) for (const k of Object.keys(prev.per_class)) keys.add(k);
  return [...keys].sort((a, b) => a.localeCompare(b));
}

export function HoldoutHistory({ history }: { history: EvalSnapshot[] }) {
  if (history.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
            Held-out accuracy over time
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            No held-out snapshots have been recorded yet. Each{" "}
            <code className="font-mono">contig eval-guard --snapshot</code>{" "}
            appends one, scoring the detector against the frozen held-out
            corpus, and the trend appears here.
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
    <section className="flex flex-col gap-4" aria-labelledby="holdout-trend-heading">
      <h2 id="holdout-trend-heading" className="font-heading text-lg font-medium">
        Held-out accuracy over time
      </h2>

      <Card>
        <CardContent className="space-y-4 pt-6">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <span className="text-xs text-muted-foreground">
              {history.length} snapshot{history.length === 1 ? "" : "s"}
            </span>
            <span className="font-mono text-sm tabular-nums">
              latest {pct(latest.accuracy)}
            </span>
          </div>
          <Sparkline
            values={history.map((s) => s.accuracy)}
            ariaLabel="Held-out detector accuracy over time"
          />
          <div className="flex justify-between text-xs text-muted-foreground tabular-nums">
            <span>{new Date(history[0].timestamp).toLocaleDateString()}</span>
            <span>
              {new Date(history[history.length - 1].timestamp).toLocaleDateString()}
            </span>
          </div>
        </CardContent>
      </Card>

      {/* Snapshot table: each row is a snapshot, newest first, with the accuracy
          delta against the previous one. */}
      <Card>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead scope="col">When</TableHead>
                <TableHead scope="col" className="text-right">
                  Held-out size
                </TableHead>
                <TableHead scope="col" className="text-right">
                  Accuracy
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
                return (
                  <TableRow key={`${snap.timestamp}-${i}`}>
                    <TableCell className="whitespace-nowrap tabular-nums">
                      {new Date(snap.timestamp).toLocaleString()}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {snap.corpus_size}
                    </TableCell>
                    <TableCell className="text-right font-medium tabular-nums">
                      {pct(snap.accuracy)}
                    </TableCell>
                    <TableCell className="text-right">
                      <DeltaCell
                        curr={snap.accuracy}
                        prev={prev ? prev.accuracy : null}
                      />
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

      {/* Per-class precision and recall deltas, latest vs the previous snapshot. */}
      <section className="flex flex-col gap-3" aria-labelledby="holdout-class-delta-heading">
        <h3
          id="holdout-class-delta-heading"
          className="font-heading text-base font-medium"
        >
          Held-out per-class change, latest snapshot
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
                      Precision
                    </TableHead>
                    <TableHead scope="col" className="text-right">
                      Precision delta
                    </TableHead>
                    <TableHead scope="col" className="text-right">
                      Recall
                    </TableHead>
                    <TableHead scope="col" className="text-right">
                      Recall delta
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
                          {curr ? pct(curr.precision) : "n/a"}
                        </TableCell>
                        <TableCell className="text-right">
                          {curr && prev ? (
                            <DeltaCell
                              curr={curr.precision}
                              prev={prev.precision}
                            />
                          ) : (
                            <span className="text-muted-foreground">
                              {curr ? "new" : "gone"}
                            </span>
                          )}
                        </TableCell>
                        <TableCell className="text-right tabular-nums">
                          {curr ? pct(curr.recall) : "n/a"}
                        </TableCell>
                        <TableCell className="text-right">
                          {curr && prev ? (
                            <DeltaCell curr={curr.recall} prev={prev.recall} />
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
