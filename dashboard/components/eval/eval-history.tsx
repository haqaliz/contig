// The eval-history trend (PRD contract D). It plots detector accuracy over time
// as an inline SVG sparkline (no chart dependency) and lists each snapshot in a
// table with per-class precision and recall deltas against the previous snapshot,
// so a regression in the detector is visible at a glance. Server Component: it
// receives the already-loaded history and renders. Empty history degrades to a
// short note. The trend is the moat's compounding signal made legible.
import { Minus, TrendingDown, TrendingUp } from "lucide-react";

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
import { cn } from "@/lib/utils";
import type { EvalSnapshot } from "@/lib/types";

function pct(value: number): string {
  return `${Math.round(value * 100)}%`;
}

/** A signed delta as a 1-decimal percentage-point string (e.g. +2.5 pp). */
function deltaPp(curr: number, prev: number): string {
  const pp = (curr - prev) * 100;
  const sign = pp > 0 ? "+" : "";
  return `${sign}${pp.toFixed(1)} pp`;
}

// Geometry for the inline sparkline. A fixed viewBox keeps the SVG crisp at any
// width because it scales with preserveAspectRatio="none" on the x axis only.
const W = 600;
const H = 140;
const PAD_X = 12;
const PAD_Y = 16;

/**
 * Map snapshots to SVG points. Accuracy is a 0..1 ratio, so the y domain is fixed
 * to [0, 1] (not min/max scaled): the line's height is honest, a 90% snapshot
 * never looks like a floor just because the other points are also high. A single
 * snapshot maps to the right edge so the dot is visible.
 */
function points(history: EvalSnapshot[]): { x: number; y: number }[] {
  const n = history.length;
  const innerW = W - PAD_X * 2;
  const innerH = H - PAD_Y * 2;
  return history.map((snap, i) => {
    const x = n === 1 ? W - PAD_X : PAD_X + (innerW * i) / (n - 1);
    const y = PAD_Y + innerH * (1 - Math.max(0, Math.min(1, snap.accuracy)));
    return { x, y };
  });
}

function Sparkline({ history }: { history: EvalSnapshot[] }) {
  const pts = points(history);
  const line = pts.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ");
  // A faint area under the line gives the trend body without a second dependency.
  const area =
    pts.length > 1
      ? `${PAD_X},${H - PAD_Y} ${line} ${(W - PAD_X).toFixed(1)},${H - PAD_Y}`
      : "";

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      preserveAspectRatio="none"
      className="h-36 w-full"
      role="img"
      aria-label="Detector accuracy over time"
    >
      {/* Gridlines at 0%, 50%, 100% for a sense of scale. */}
      {[0, 0.5, 1].map((g) => {
        const y = PAD_Y + (H - PAD_Y * 2) * (1 - g);
        return (
          <line
            key={g}
            x1={PAD_X}
            x2={W - PAD_X}
            y1={y}
            y2={y}
            className="stroke-border"
            strokeWidth={1}
            strokeDasharray="3 3"
          />
        );
      })}
      {area ? <polygon points={area} className="fill-brand/10" /> : null}
      {pts.length > 1 ? (
        <polyline
          points={line}
          fill="none"
          className="stroke-brand"
          strokeWidth={2}
          strokeLinejoin="round"
          strokeLinecap="round"
          vectorEffect="non-scaling-stroke"
        />
      ) : null}
      {pts.map((p, i) => (
        <circle
          key={i}
          cx={p.x}
          cy={p.y}
          r={3}
          className="fill-brand"
          vectorEffect="non-scaling-stroke"
        />
      ))}
    </svg>
  );
}

// A small trend glyph for a delta: up for a gain, down for a drop, dash for flat.
function DeltaCell({ curr, prev }: { curr: number; prev: number | null }) {
  if (prev === null) {
    return <span className="text-muted-foreground tabular-nums">first</span>;
  }
  const diff = curr - prev;
  const flat = Math.abs(diff) < 0.005;
  const Icon = flat ? Minus : diff > 0 ? TrendingUp : TrendingDown;
  return (
    <span
      className={cn(
        "inline-flex items-center justify-end gap-1 tabular-nums",
        flat
          ? "text-muted-foreground"
          : diff > 0
            ? "text-emerald-700 dark:text-emerald-400"
            : "text-destructive",
      )}
    >
      <Icon className="size-3.5" aria-hidden="true" />
      {flat ? "0.0 pp" : deltaPp(curr, prev)}
    </span>
  );
}

// Every class seen across the two snapshots being compared, sorted, so a class
// that appeared or vanished still shows a row.
function classKeys(
  curr: EvalSnapshot,
  prev: EvalSnapshot | null,
): string[] {
  const keys = new Set<string>(Object.keys(curr.per_class));
  if (prev) for (const k of Object.keys(prev.per_class)) keys.add(k);
  return [...keys].sort((a, b) => a.localeCompare(b));
}

export function EvalHistory({ history }: { history: EvalSnapshot[] }) {
  if (history.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
            Accuracy over time
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            No eval snapshots have been recorded yet. Each{" "}
            <code className="font-mono">contig eval-detector --snapshot</code>{" "}
            (and every corpus promote) appends one, and the trend appears here.
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
    <section className="flex flex-col gap-4" aria-labelledby="trend-heading">
      <h2 id="trend-heading" className="font-heading text-lg font-medium">
        Accuracy over time
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
          <Sparkline history={history} />
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
                  Corpus size
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
      <section className="flex flex-col gap-3" aria-labelledby="class-delta-heading">
        <h3
          id="class-delta-heading"
          className="font-heading text-base font-medium"
        >
          Per-class change, latest snapshot
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
