"use client";

// The self-heal confirm gate (PRD contract C). When a run pauses awaiting
// approval, the live feed renders the proposed patch (kind, risk, rationale, and
// the diagnosis it answers) with Approve and Reject. A safe patch would have
// auto-applied, so anything that reaches this gate is needs_confirmation or
// destructive. A destructive patch requires a SECOND confirm before Approve
// fires: the first click arms a "Confirm destructive approve" step, the second
// sends it. The decision POSTs to /api/runs/[id]/approve, which shells the CLI to
// write approval.json; the engine's poll then unblocks and the run continues.
import { useState } from "react";
import { useRouter } from "next/navigation";
import { AlertTriangle, Check, Loader2, ShieldAlert, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import type { PendingApproval } from "@/lib/types";

// Friendly labels for the engine's machine failure classes (kept in sync with the
// running view and the repair timeline so every surface reads the same).
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

// The risk badge: a destructive patch reads as a hard warning, needs_confirmation
// as a softer caution, anything else as a neutral note.
function riskVariant(risk: string): "destructive" | "outline" | "secondary" {
  if (risk === "destructive") return "destructive";
  if (risk === "needs_confirmation") return "outline";
  return "secondary";
}

export function ApprovalGate({
  id,
  pending,
}: {
  id: string;
  pending: PendingApproval;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState<"approve" | "reject" | null>(null);
  const [error, setError] = useState<string | null>(null);
  // For a destructive patch, the first Approve click arms this confirm step; the
  // second click actually sends. Non-destructive patches skip straight to send.
  const [armed, setArmed] = useState(false);

  const destructive = pending.patch.risk === "destructive";

  async function decide(decision: "approve" | "reject") {
    setBusy(decision);
    setError(null);
    try {
      const res = await fetch(`/api/runs/${encodeURIComponent(id)}/approve`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ decision }),
      });
      if (res.ok) {
        // The engine unblocks and the run continues (approve) or finalizes
        // (reject); refresh so the page re-renders into the new state.
        router.refresh();
        return;
      }
      const data = (await res.json().catch(() => ({}))) as { error?: string };
      setError(data.error ?? "Could not record the decision.");
      setBusy(null);
      setArmed(false);
    } catch {
      setError("Could not record the decision.");
      setBusy(null);
      setArmed(false);
    }
  }

  function onApprove() {
    // A destructive patch needs a second confirm: arm on the first click, send on
    // the second. Everything else sends immediately.
    if (destructive && !armed) {
      setArmed(true);
      return;
    }
    void decide("approve");
  }

  return (
    <Card className="border-amber-300 dark:border-amber-800">
      <CardContent className="space-y-4 py-5">
        <div className="flex flex-wrap items-center gap-2">
          <ShieldAlert
            className="size-4 text-amber-600 dark:text-amber-400"
            aria-hidden="true"
          />
          <h3 className="text-sm font-medium">
            This run is paused for your approval
          </h3>
          <Badge variant="outline" className="font-medium">
            Attempt {pending.attempt}
          </Badge>
        </div>

        <p className="text-sm text-muted-foreground">
          A safe fix was not available, so Contig is holding the run until you
          approve or reject this repair. Nothing risky is applied without your
          say.
        </p>

        {/* The diagnosis this patch answers. */}
        <div className="rounded-lg bg-muted/50 px-3 py-2.5">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="outline" className="font-medium">
              {failureLabel(pending.diagnosis.failure_class)}
            </Badge>
            <span className="text-xs text-muted-foreground tabular-nums">
              confidence {Math.round(pending.diagnosis.confidence * 100)}%
            </span>
          </div>
          <p className="mt-1.5 text-sm text-muted-foreground">
            {pending.diagnosis.root_cause}
          </p>
        </div>

        {/* The proposed patch: kind, risk, and the rationale for it. */}
        <div className="space-y-2 rounded-lg ring-1 ring-foreground/10 px-3 py-2.5">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-mono text-sm font-medium">
              {pending.patch.kind}
            </span>
            <Badge
              variant={riskVariant(pending.patch.risk)}
              className="font-medium"
            >
              {pending.patch.risk.replace(/_/g, " ")}
            </Badge>
          </div>
          <p className="text-sm text-muted-foreground">
            {pending.patch.rationale}
          </p>
          <p className="text-xs text-muted-foreground">
            Expected signal: {pending.patch.expected_signal}
          </p>
        </div>

        {destructive ? (
          <p className="flex items-start gap-2 text-sm text-destructive">
            <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
            <span>
              This patch is marked destructive. Approving it can discard work or
              data, so it asks for a second confirm.
            </span>
          </p>
        ) : null}

        <div className="flex flex-wrap items-center gap-3">
          <Button
            type="button"
            variant={destructive ? "destructive" : "default"}
            onClick={onApprove}
            disabled={busy !== null}
          >
            {busy === "approve" ? (
              <Loader2 className="size-4 animate-spin" aria-hidden="true" />
            ) : (
              <Check className="size-4" aria-hidden="true" />
            )}
            {destructive && armed ? "Confirm destructive approve" : "Approve"}
          </Button>
          <Button
            type="button"
            variant="outline"
            onClick={() => void decide("reject")}
            disabled={busy !== null}
          >
            {busy === "reject" ? (
              <Loader2 className="size-4 animate-spin" aria-hidden="true" />
            ) : (
              <X className="size-4" aria-hidden="true" />
            )}
            Reject
          </Button>
          {destructive && armed && busy === null ? (
            <button
              type="button"
              onClick={() => setArmed(false)}
              className="rounded-sm text-sm text-muted-foreground underline-offset-4 transition-colors hover:text-foreground hover:underline focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none"
            >
              Cancel
            </button>
          ) : null}
        </div>

        {error ? (
          <p
            role="alert"
            className="rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive"
          >
            {error}
          </p>
        ) : null}
      </CardContent>
    </Card>
  );
}
