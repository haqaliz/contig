"use client";

// Corpus coverage panel (PRD contract C). The engine reports per-class support, the
// thin classes (fewer than 3 cases, a coverage gap), the by-source breakdown, and a
// confirmed-over-time series. The dashboard never computes coverage itself: this
// panel fetches /api/eval/coverage, which shells `contig coverage --json`, and
// renders per-class support bars with the thin classes flagged. An unavailable CLI
// degrades to a quiet notice rather than an error.
import { useEffect, useState } from "react";
import { AlertTriangle, Layers } from "lucide-react";

import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { CoverageReport } from "@/lib/types";

type Phase = "loading" | "loaded" | "unavailable";

export function CoveragePanel() {
  const [phase, setPhase] = useState<Phase>("loading");
  const [report, setReport] = useState<CoverageReport | null>(null);

  useEffect(() => {
    let active = true;
    void (async () => {
      try {
        const res = await fetch("/api/eval/coverage");
        if (!active) return;
        if (res.ok) {
          setReport((await res.json()) as CoverageReport);
          setPhase("loaded");
          return;
        }
        setPhase("unavailable");
      } catch {
        if (active) setPhase("unavailable");
      }
    })();
    return () => {
      active = false;
    };
  }, []);

  // Sort classes by support, biggest first, so the best-covered modes lead and the
  // thin tail is visible at a glance. The widest bar normalizes the rest.
  const classes = report
    ? Object.entries(report.per_class).sort(([, a], [, b]) => b - a)
    : [];
  const max = classes.reduce((m, [, count]) => Math.max(m, count), 0);
  const thin = new Set(report?.thin ?? []);

  return (
    <section
      className="flex flex-col gap-3"
      aria-labelledby="coverage-heading"
      data-testid="coverage-panel"
    >
      <h2 id="coverage-heading" className="font-heading text-lg font-medium">
        Corpus coverage
      </h2>
      <Card>
        <CardHeader className="border-b pb-4">
          <CardTitle className="flex items-center justify-between gap-2 text-xs font-medium tracking-wide text-muted-foreground uppercase">
            <span className="flex items-center gap-2">
              <Layers className="size-4" aria-hidden="true" />
              Per-class support
            </span>
            {report ? (
              <span className="tabular-nums">
                {report.total} {report.total === 1 ? "case" : "cases"}
              </span>
            ) : null}
          </CardTitle>
        </CardHeader>
        <CardContent className="pt-5">
          {phase === "loading" ? (
            <p className="text-sm text-muted-foreground">Loading coverage.</p>
          ) : phase === "unavailable" || !report ? (
            <p className="text-sm text-muted-foreground">
              Coverage is unavailable because the{" "}
              <code className="font-mono">contig coverage</code> CLI could not run.
            </p>
          ) : classes.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              The corpus has no cases yet, so there is no coverage to report.
            </p>
          ) : (
            <ul className="flex flex-col gap-3">
              {classes.map(([name, count]) => {
                const isThin = thin.has(name);
                const width = max > 0 ? Math.max(4, (count / max) * 100) : 0;
                return (
                  <li key={name} className="flex flex-col gap-1">
                    <div className="flex items-center justify-between gap-2 text-sm">
                      <span className="flex items-center gap-1.5 font-mono">
                        {isThin ? (
                          <AlertTriangle
                            className="size-3.5 text-amber-600 dark:text-amber-400"
                            aria-label="Thin coverage"
                          />
                        ) : null}
                        {name}
                      </span>
                      <span className="tabular-nums text-muted-foreground">
                        {count}
                      </span>
                    </div>
                    <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
                      <div
                        className={cn(
                          "h-full rounded-full",
                          isThin ? "bg-amber-400 dark:bg-amber-500" : "bg-primary",
                        )}
                        style={{ width: `${width}%` }}
                      />
                    </div>
                  </li>
                );
              })}
            </ul>
          )}

          {report && report.thin.length > 0 ? (
            <div className="mt-5 flex flex-wrap items-center gap-2 border-t pt-4">
              <span className="flex items-center gap-1.5 text-sm font-medium text-amber-700 dark:text-amber-400">
                <AlertTriangle className="size-4" aria-hidden="true" />
                Thin coverage
              </span>
              <span className="text-sm text-muted-foreground">
                fewer than 3 cases, a gap to fill:
              </span>
              {report.thin.map((name) => (
                <Badge key={name} variant="outline" className="font-mono">
                  {name}
                </Badge>
              ))}
            </div>
          ) : null}

          {report && Object.keys(report.by_source).length > 0 ? (
            <div className="mt-5 border-t pt-4">
              <h3 className="mb-2 text-xs font-medium tracking-wide text-muted-foreground uppercase">
                By source
              </h3>
              <div className="flex flex-wrap gap-2">
                {Object.entries(report.by_source)
                  .sort(([, a], [, b]) => b - a)
                  .map(([source, count]) => (
                    <Badge key={source} variant="secondary" className="gap-1.5">
                      <span className="font-mono">{source}</span>
                      <span className="tabular-nums">{count}</span>
                    </Badge>
                  ))}
              </div>
            </div>
          ) : null}
        </CardContent>
      </Card>
    </section>
  );
}
