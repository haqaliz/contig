"use client";

// Shown while a run is in flight (status.json says "running", no bundle yet).
// It polls /api/runs/[id]/progress and renders a live summary: elapsed time,
// tasks completed, the steps currently running, live self-heal attempts, and a
// collapsible log tail (a handle opens/closes it so the noisy log can be
// calmed). It stays honest: it shows the completed count and the running steps,
// it never fabricates a percentage when the total task count is unknown. When
// the run finishes (the progress state leaves "running"), it calls
// router.refresh so the page re-renders into the normal run detail.
import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { ChevronDown, Loader2, Wrench } from "lucide-react";

import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { ApprovalGate } from "@/components/run/approval-gate";
import { CancelButton } from "@/components/run/cancel-button";
import type { PendingApproval, RunProgress } from "@/lib/types";

// Friendly labels for the engine's machine failure classes (mirrors the repair
// timeline so the live view and the final record read the same).
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

function formatElapsed(sec: number | null): string {
  if (sec === null) return "just started";
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  const s = sec % 60;
  const parts: string[] = [];
  if (h > 0) parts.push(`${h}h`);
  if (h > 0 || m > 0) parts.push(`${m}m`);
  parts.push(`${s}s`);
  return parts.join(" ");
}

interface ProgressResponse {
  progress: RunProgress;
  logTail: string;
  pendingApproval: PendingApproval | null;
}

export function RunningView({
  id,
  startedAt,
}: {
  id: string;
  startedAt?: string;
}) {
  const router = useRouter();
  const [progress, setProgress] = useState<RunProgress | null>(null);
  const [logTail, setLogTail] = useState("");
  const [pending, setPending] = useState<PendingApproval | null>(null);
  const [logOpen, setLogOpen] = useState(false);
  const refreshed = useRef(false);

  const poll = useCallback(async () => {
    try {
      const res = await fetch(`/api/runs/${encodeURIComponent(id)}/progress`, {
        cache: "no-store",
      });
      if (!res.ok) return;
      const data = (await res.json()) as ProgressResponse;
      setProgress(data.progress);
      setLogTail(data.logTail);
      setPending(data.pendingApproval);
      // A paused run (awaiting_approval) is still in flight: stay on this view so
      // the approval gate shows. Only a truly terminal or dead state (finished,
      // cancelled, interrupted, missing) swaps views via a one-time refresh.
      const stillLive =
        data.progress.state === "running" ||
        data.progress.state === "awaiting_approval";
      if (!stillLive && !refreshed.current) {
        refreshed.current = true;
        router.refresh();
      }
    } catch {
      // A transient fetch failure just skips this tick; the next one retries.
    }
  }, [id, router]);

  useEffect(() => {
    // Kick the first poll off the effect's synchronous path (a 0ms timer) so the
    // initial state update lands in a later tick, then poll on an interval.
    const first = setTimeout(() => void poll(), 0);
    const t = setInterval(() => void poll(), 3000);
    return () => {
      clearTimeout(first);
      clearInterval(t);
    };
  }, [poll]);

  const elapsed = progress
    ? formatElapsed(progress.elapsedSec)
    : startedAt
      ? "running"
      : "just started";
  const running = progress?.tasksRunning ?? [];
  const completed = progress?.tasksCompleted ?? 0;
  const repairs = progress?.repairs ?? [];
  // The run is paused on a gated patch when the polled state says so and a pending
  // approval has landed. While paused we lead with the gate, not the spinner.
  const awaiting = progress?.state === "awaiting_approval";

  return (
    <div className="space-y-4" aria-live="polite">
      {awaiting && pending ? <ApprovalGate id={id} pending={pending} /> : null}

      <Card>
        <CardContent className="space-y-5 py-6">
          <div className="flex flex-wrap items-center gap-3">
            <Loader2 className="size-5 animate-spin text-brand" aria-hidden="true" />
            <p className="text-base font-medium">
              {awaiting
                ? "This run is paused, awaiting your approval"
                : "This run is in progress"}
            </p>
          </div>
          <p className="text-sm text-muted-foreground">
            {awaiting
              ? "Contig has paused the self-heal loop on a repair that needs your decision. Approve or reject it above; the run continues automatically."
              : "Contig is running the pipeline and will self-heal and verify it. The verdict appears here automatically when it finishes."}
          </p>

          <CancelButton id={id} />

          <dl className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            <div className="rounded-lg bg-muted/50 px-3 py-2.5">
              <dt className="text-xs text-muted-foreground">Elapsed</dt>
              <dd className="mt-0.5 font-mono text-sm tabular-nums">{elapsed}</dd>
            </div>
            <div className="rounded-lg bg-muted/50 px-3 py-2.5">
              <dt className="text-xs text-muted-foreground">Tasks completed</dt>
              <dd className="mt-0.5 font-mono text-sm tabular-nums">{completed}</dd>
            </div>
            <div className="rounded-lg bg-muted/50 px-3 py-2.5">
              <dt className="text-xs text-muted-foreground">Self-heal attempts</dt>
              <dd className="mt-0.5 font-mono text-sm tabular-nums">{repairs.length}</dd>
            </div>
          </dl>

          {startedAt ? (
            <p className="text-xs text-muted-foreground">
              Started {new Date(startedAt).toLocaleString()}
            </p>
          ) : null}
        </CardContent>
      </Card>

      {running.length > 0 ? (
        <Card>
          <CardContent className="space-y-2 py-5">
            <h3 className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
              Currently running ({running.length})
            </h3>
            <ul className="space-y-1.5">
              {running.map((t, i) => (
                <li
                  key={`${t.process}-${t.name ?? i}`}
                  className="flex items-center gap-2 text-sm"
                >
                  <Loader2
                    className="size-3.5 animate-spin text-muted-foreground"
                    aria-hidden="true"
                  />
                  <span className="font-mono">{t.name ?? t.process}</span>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      ) : null}

      {repairs.length > 0 ? (
        <Card>
          <CardContent className="space-y-3 py-5">
            <h3 className="flex items-center gap-2 text-xs font-medium tracking-wide text-muted-foreground uppercase">
              <Wrench className="size-3.5" aria-hidden="true" />
              Self-healing in progress
            </h3>
            <ul className="space-y-2">
              {repairs.map((step) => (
                <li
                  key={step.attempt}
                  className="space-y-1 rounded-lg ring-1 ring-foreground/10 px-3 py-2"
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-sm font-medium">
                      Attempt {step.attempt}
                    </span>
                    <Badge variant="outline" className="font-medium">
                      {failureLabel(step.diagnosis.failure_class)}
                    </Badge>
                    <span className="text-xs text-muted-foreground">
                      {step.outcome.replace(/_/g, " ")}
                    </span>
                  </div>
                  <p className="text-sm text-muted-foreground">
                    {step.diagnosis.root_cause}
                  </p>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      ) : null}

      <Card>
        <CardContent className="py-4">
          <Collapsible open={logOpen} onOpenChange={setLogOpen}>
            <CollapsibleTrigger
              className={cn(
                "flex w-full items-center gap-2 rounded-sm text-left text-sm font-medium text-muted-foreground outline-none transition-colors hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring/50",
              )}
            >
              <ChevronDown
                className={cn(
                  "size-4 transition-transform",
                  logOpen ? "rotate-0" : "-rotate-90",
                )}
                aria-hidden="true"
              />
              {logOpen ? "Hide log tail" : "Show log tail"}
            </CollapsibleTrigger>
            <CollapsibleContent className="pt-3">
              {logTail.trim().length > 0 ? (
                <pre className="max-h-80 overflow-auto rounded-lg bg-muted/60 px-3 py-2 font-mono text-xs whitespace-pre-wrap break-words">
                  {logTail}
                </pre>
              ) : (
                <p className="text-sm text-muted-foreground">
                  No log output yet.
                </p>
              )}
            </CollapsibleContent>
          </Collapsible>
        </CardContent>
      </Card>
    </div>
  );
}
