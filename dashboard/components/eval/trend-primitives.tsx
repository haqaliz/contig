// Small shared helpers for the /eval trend cards (holdout accuracy, self-heal
// outcome-match): a fixed-domain [0,1] inline SVG sparkline, a percentage
// formatter, and a signed percentage-point delta indicator. Deliberately
// duplicated out of eval-history.tsx rather than imported from it, so the
// tested detector trend stays untouched while these two new trends share one
// source of truth for their geometry and formatting.
import { Minus, TrendingDown, TrendingUp } from "lucide-react";

import { cn } from "@/lib/utils";

export function pct(value: number): string {
  return `${Math.round(value * 100)}%`;
}

/** A signed delta as a 1-decimal percentage-point string (e.g. +2.5 pp). */
export function deltaPp(curr: number, prev: number): string {
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
 * Map a 0..1 value series to SVG points. The y domain is fixed to [0, 1] (not
 * min/max scaled): the line's height is honest, a 90% snapshot never looks
 * like a floor just because the other points are also high. A single value
 * maps to the right edge so the dot is visible.
 */
function points(values: number[]): { x: number; y: number }[] {
  const n = values.length;
  const innerW = W - PAD_X * 2;
  const innerH = H - PAD_Y * 2;
  return values.map((value, i) => {
    const x = n === 1 ? W - PAD_X : PAD_X + (innerW * i) / (n - 1);
    const y = PAD_Y + innerH * (1 - Math.max(0, Math.min(1, value)));
    return { x, y };
  });
}

/** A fixed-domain [0,1] sparkline over a value series, in chronological order. */
export function Sparkline({
  values,
  ariaLabel,
}: {
  values: number[];
  ariaLabel: string;
}) {
  const pts = points(values);
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
      aria-label={ariaLabel}
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
export function DeltaCell({
  curr,
  prev,
}: {
  curr: number;
  prev: number | null;
}) {
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
