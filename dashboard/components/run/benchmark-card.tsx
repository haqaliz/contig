"use client";

// Cross-run benchmark for a finished run (PRD contract A). The engine compares the
// run against the designated reference for its (pipeline, assay) by QC metric
// values within a relative tolerance plus structural shape, robust to run-to-run
// non-determinism. The dashboard never compares anything itself: this card fetches
// /api/runs/[id]/benchmark, which shells `contig benchmark <id> --json`, and renders
// the {reference_run_id, tolerance, matched, drifted, checks, status} report.
//
// Three resting states, by report.status:
//   no_reference  no reference is recorded for this run's pipeline/assay, so there
//                 is nothing to compare against (a neutral state, never a fail).
//   match         every shared metric is within tolerance and the shape matches.
//   drift         at least one shared metric is out of tolerance, or the shape
//                 differs (a check present in one run but not the other).
// The card fetches on mount so the comparison shows without a click; the CLI being
// unavailable degrades to a quiet notice rather than an error.
import { useEffect, useState } from "react";
import { GitCompareArrows, CheckCircle2, AlertTriangle, Minus } from "lucide-react";

import { Badge } from "@/components/ui/badge";
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
import { cn } from "@/lib/utils";
import type { BenchmarkReport } from "@/lib/types";

type Phase = "loading" | "loaded" | "unavailable";

/** Render a metric value compactly: a plain number, or an em-free dash for null. */
function fmt(value: number | null): string {
  if (value === null || Number.isNaN(value)) return "n/a";
  // Trim trailing zeros so 0.5 reads as "0.5" and 12 reads as "12".
  return Number.isInteger(value) ? String(value) : String(Number(value.toFixed(4)));
}

export function BenchmarkCard({ id }: { id: string }) {
  const [phase, setPhase] = useState<Phase>("loading");
  const [report, setReport] = useState<BenchmarkReport | null>(null);

  useEffect(() => {
    let active = true;
    void (async () => {
      try {
        const res = await fetch(
          `/api/runs/${encodeURIComponent(id)}/benchmark`,
        );
        if (!active) return;
        if (res.ok) {
          setReport((await res.json()) as BenchmarkReport);
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
  }, [id]);

  const status = report?.status ?? null;
  const drift = status === "drift";
  const match = status === "match";
  const noReference = status === "no_reference";

  return (
    <Card aria-labelledby="benchmark-title" data-testid="benchmark-card">
      <CardHeader className="gap-3 border-b pb-4">
        <CardTitle
          id="benchmark-title"
          className="flex flex-wrap items-center gap-3 text-lg"
        >
          {match ? (
            <Badge
              variant="outline"
              className="gap-1 border-emerald-300 bg-emerald-50 px-3 py-1 text-sm font-medium text-emerald-800 dark:border-emerald-800 dark:bg-emerald-950 dark:text-emerald-300"
            >
              <CheckCircle2 className="size-4" aria-hidden="true" />
              Matches reference
            </Badge>
          ) : drift ? (
            <Badge
              variant="outline"
              className="gap-1 border-amber-300 bg-amber-50 px-3 py-1 text-sm font-medium text-amber-800 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-300"
            >
              <AlertTriangle className="size-4" aria-hidden="true" />
              Drift detected
            </Badge>
          ) : (
            <Badge
              variant="outline"
              className="gap-1 border-slate-300 bg-slate-50 px-3 py-1 text-sm font-medium text-slate-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300"
            >
              <Minus className="size-4" aria-hidden="true" />
              No reference
            </Badge>
          )}
          <span className="text-muted-foreground text-xs font-medium tracking-wide uppercase">
            Cross-run benchmark
          </span>
        </CardTitle>
        <CardDescription className="text-base leading-relaxed text-foreground">
          {phase === "loading"
            ? "Comparing this run against the reference for its pipeline and assay."
            : noReference
              ? "No reference run is set for this pipeline and assay, so there is nothing to compare against yet. Set this run as the reference to benchmark future runs against it."
              : match && report
                ? `Every shared QC metric is within the ${Math.round(report.tolerance * 100)}% tolerance of the reference, and the set of checks matches. This run is consistent with the reference.`
                : drift && report
                  ? `At least one QC metric drifted beyond the ${Math.round(report.tolerance * 100)}% tolerance, or the set of checks differs from the reference. Review the metrics below.`
                  : "The benchmark could not be produced because the contig benchmark CLI was unavailable."}
        </CardDescription>
      </CardHeader>
      <CardContent className="pt-5">
        {phase === "loaded" && report && report.reference_run_id ? (
          <p className="mb-4 text-sm text-muted-foreground">
            Reference run:{" "}
            <span className="font-mono text-foreground break-all">
              {report.reference_run_id}
            </span>
            <span className="ml-2 tabular-nums">
              ({report.matched} within tolerance, {report.drifted} drifted)
            </span>
          </p>
        ) : null}

        {phase === "loaded" && report && report.checks.length > 0 ? (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead scope="col">Metric</TableHead>
                <TableHead scope="col" className="text-right">
                  This run
                </TableHead>
                <TableHead scope="col" className="text-right">
                  Reference
                </TableHead>
                <TableHead scope="col" className="text-right">
                  Delta
                </TableHead>
                <TableHead scope="col" className="text-right">
                  Status
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {report.checks.map((check) => (
                <TableRow
                  key={check.name}
                  className={cn(
                    !check.within_tolerance &&
                      "bg-amber-50/60 dark:bg-amber-950/30",
                  )}
                >
                  <TableHead scope="row" className="font-medium whitespace-normal">
                    <span className="font-mono">{check.name}</span>
                  </TableHead>
                  <TableCell className="text-right tabular-nums">
                    {fmt(check.run_value)}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {fmt(check.reference_value)}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {check.delta === null ? "n/a" : fmt(check.delta)}
                  </TableCell>
                  <TableCell className="text-right">
                    {check.within_tolerance ? (
                      <span className="inline-flex items-center gap-1 text-sm text-emerald-700 dark:text-emerald-400">
                        <CheckCircle2 className="size-3.5" aria-hidden="true" />
                        within
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 text-sm text-amber-700 dark:text-amber-400">
                        <AlertTriangle className="size-3.5" aria-hidden="true" />
                        drift
                      </span>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        ) : phase === "loaded" && !noReference && report ? (
          <p className="flex items-center gap-2 text-sm text-muted-foreground">
            <GitCompareArrows className="size-4 shrink-0" aria-hidden="true" />
            No shared QC metrics to compare between this run and the reference.
          </p>
        ) : null}
      </CardContent>
    </Card>
  );
}
