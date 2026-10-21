// The verify verdict-match trend (C6 verify regression guard). It plots the
// verification rules' verdict-match rate against the labeled corpus over time as
// an inline SVG sparkline and lists each snapshot with per-family deltas. This
// is distinct from EvalHistory (detector accuracy) and HealHistory (self-heal
// outcome-match): it asks whether the rules reproduce the labeled verdicts.
// Server Component: it receives the already-loaded history and renders. No
// history means no card (nothing has been recorded to trend).
import { Card, CardContent } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { VerifySnapshot } from "@/lib/types";
import { DeltaCell, Sparkline, pct } from "@/components/eval/trend-primitives";

// Every family seen across the two snapshots being compared, sorted, so a
// family that appeared or vanished still shows a row.
function familyKeys(
  curr: VerifySnapshot,
  prev: VerifySnapshot | null,
): string[] {
  const keys = new Set<string>(Object.keys(curr.per_family));
  if (prev) for (const k of Object.keys(prev.per_family)) keys.add(k);
  return [...keys].sort((a, b) => a.localeCompare(b));
}

export function VerifyHistory({ history }: { history: VerifySnapshot[] }) {
  if (history.length === 0) return null;

  // Newest first for the table; the latest snapshot is compared to the one before
  // it. The sparkline keeps file (chronological) order so time reads left to right.
  const newestFirst = [...history].reverse();
  const latest = newestFirst[0];
  const previous = newestFirst.length > 1 ? newestFirst[1] : null;

  return (
    <section className="flex flex-col gap-4" aria-labelledby="verify-trend-heading">
      <h2 id="verify-trend-heading" className="font-heading text-lg font-medium">
        Verify verdict-match over time
      </h2>

      <Card>
        <CardContent className="space-y-4 pt-6">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <span className="text-xs text-muted-foreground">
              {history.length} snapshot{history.length === 1 ? "" : "s"}
            </span>
            <span className="font-mono text-sm tabular-nums">
              latest {pct(latest.verdict_match_rate)}
            </span>
          </div>
          <Sparkline
            values={history.map((s) => s.verdict_match_rate)}
            ariaLabel="Verify verdict-match over time"
          />
          <div className="flex justify-between text-xs text-muted-foreground tabular-nums">
            <span>{new Date(history[0].timestamp).toLocaleDateString()}</span>
            <span>
              {new Date(history[history.length - 1].timestamp).toLocaleDateString()}
            </span>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead scope="col">When</TableHead>
                <TableHead scope="col" className="text-right">
                  Cases
                </TableHead>
                <TableHead scope="col" className="text-right">
                  Verdict-match
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
                      {snap.case_count}
                    </TableCell>
                    <TableCell className="text-right font-medium tabular-nums">
                      {pct(snap.verdict_match_rate)}
                    </TableCell>
                    <TableCell className="text-right">
                      <DeltaCell
                        curr={snap.verdict_match_rate}
                        prev={prev ? prev.verdict_match_rate : null}
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

      {/* Per-family verdict-match deltas, latest vs the previous snapshot. */}
      <section
        className="flex flex-col gap-3"
        aria-labelledby="verify-family-delta-heading"
      >
        <h3
          id="verify-family-delta-heading"
          className="font-heading text-base font-medium"
        >
          Verify per-family change, latest snapshot
        </h3>
        <Card>
          <CardContent>
            {previous === null ? (
              <p className="text-sm text-muted-foreground">
                Only one snapshot so far, so there is nothing to compare against
                yet. The next snapshot will show per-family movement here.
              </p>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead scope="col">Family</TableHead>
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
                  {familyKeys(latest, previous).map((name) => {
                    const curr = latest.per_family[name];
                    const prev = previous.per_family[name];
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
