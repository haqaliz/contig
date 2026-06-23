"use client";

// Recurring failure modes (PRD contract B). The engine groups corpus and pending
// cases by failure class plus a normalized log signature (lowercase, absolute
// paths, numbers, hashes, and timestamps stripped, salient lines hashed), so the
// same systemic failure mode groups even across runs, and orders them worst first
// (largest count). The dashboard never clusters anything itself: this view fetches
// /api/eval/clusters, which shells `contig clusters --json`, and lists the modes
// with their case counts. An unavailable CLI degrades to a quiet notice.
import { useEffect, useState } from "react";
import { Boxes } from "lucide-react";

import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import type { FailureCluster } from "@/lib/types";

// Friendly labels for the engine's machine failure classes (kept in sync with the
// approval gate and the repair timeline so every surface reads the same).
const FAILURE_LABELS: Record<string, string> = {
  oom: "Out of memory",
  time_limit: "Time limit",
  missing_reference: "Missing reference",
  missing_index: "Missing index",
  bad_param: "Bad parameter",
  container_pull_failed: "Container pull failed",
  container_unavailable: "Container unavailable",
  conda_solve_failed: "Conda solve failed",
  platform_unsupported: "Platform unsupported",
  tool_crash: "Tool crashed",
  no_progress: "No progress",
  qc_anomaly: "QC anomaly",
  unknown: "Unknown failure",
};

function failureLabel(failureClass: string): string {
  return (
    FAILURE_LABELS[failureClass] ??
    failureClass.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())
  );
}

type Phase = "loading" | "loaded" | "unavailable";

export function ClustersView() {
  const [phase, setPhase] = useState<Phase>("loading");
  const [clusters, setClusters] = useState<FailureCluster[]>([]);

  useEffect(() => {
    let active = true;
    void (async () => {
      try {
        const res = await fetch("/api/eval/clusters");
        if (!active) return;
        if (res.ok) {
          setClusters((await res.json()) as FailureCluster[]);
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

  return (
    <section
      className="flex flex-col gap-3"
      aria-labelledby="clusters-heading"
      data-testid="clusters-view"
    >
      <h2 id="clusters-heading" className="font-heading text-lg font-medium">
        Recurring failure modes
      </h2>
      <Card>
        <CardHeader className="border-b pb-4">
          <CardTitle className="flex items-center gap-2 text-xs font-medium tracking-wide text-muted-foreground uppercase">
            <Boxes className="size-4" aria-hidden="true" />
            Failure clusters, worst first
          </CardTitle>
        </CardHeader>
        <CardContent className="pt-5">
          {phase === "loading" ? (
            <p className="text-sm text-muted-foreground">Loading clusters.</p>
          ) : phase === "unavailable" ? (
            <p className="text-sm text-muted-foreground">
              Clusters are unavailable because the{" "}
              <code className="font-mono">contig clusters</code> CLI could not run.
            </p>
          ) : clusters.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No recurring failure modes yet. Cases group here as the corpus grows.
            </p>
          ) : (
            <ul className="flex flex-col divide-y">
              {clusters.map((cluster) => (
                <li
                  key={`${cluster.failure_class}:${cluster.signature}`}
                  className="flex flex-col gap-2 py-4 first:pt-0 last:pb-0"
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant="outline" className="font-medium">
                      {failureLabel(cluster.failure_class)}
                    </Badge>
                    <span className="text-sm text-muted-foreground tabular-nums">
                      {cluster.count} {cluster.count === 1 ? "case" : "cases"}
                    </span>
                    <span className="font-mono text-xs text-muted-foreground break-all">
                      {cluster.signature}
                    </span>
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {cluster.case_ids.map((caseId) => (
                      <Badge
                        key={caseId}
                        variant="secondary"
                        className="font-mono text-xs"
                      >
                        {caseId}
                      </Badge>
                    ))}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </section>
  );
}
