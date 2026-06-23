"use client";

// The self-heal confirm gate (PRD contracts C and D). When a run pauses awaiting
// approval, the live feed renders the gate. A safe patch would have auto-applied,
// so anything that reaches this gate is needs_confirmation, destructive, or an
// ambiguous decision.
//
// Two shapes share this component, by pending.decision_kind:
//   - "single" (or absent): one proposed patch (kind, risk, rationale, and the
//     diagnosis it answers) with Approve and Reject. A destructive patch needs a
//     SECOND confirm before Approve fires.
//   - "choice": the decision was ambiguous, so the ranked options (best first) are
//     rendered as a choice list. The human picks one, then Approve sends the chosen
//     index (`contig approve --choose N`). A destructive chosen option still needs
//     a second confirm.
// The decision POSTs to /api/runs/[id]/approve, which shells the CLI to write
// approval.json; the engine's poll then unblocks and the run continues.
import { useState } from "react";
import { useRouter } from "next/navigation";
import { AlertTriangle, Check, Loader2, ShieldAlert, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { ApprovalOption, PendingApproval } from "@/lib/types";

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
  // For a destructive approve, the first click arms this confirm step; the second
  // click actually sends. A non-destructive approve skips straight to send.
  const [armed, setArmed] = useState(false);

  // A guided-escalation choice (PRD contract D): the engine wrote ranked options and
  // the human picks one. Otherwise this is the single binary gate over pending.patch.
  const options =
    pending.decision_kind === "choice" &&
    Array.isArray(pending.options) &&
    pending.options.length > 0
      ? pending.options
      : null;
  // The currently selected option index in choice mode; the first (best) is
  // pre-selected so a single Approve is the common path. Null in single mode.
  const [selected, setSelected] = useState<number>(options ? options[0].index : 0);

  // The risk that gates a second confirm: in choice mode the selected option's
  // risk, in single mode the patch's risk.
  const selectedOption = options
    ? options.find((o) => o.index === selected) ?? options[0]
    : null;
  const destructive = options
    ? selectedOption?.risk === "destructive"
    : pending.patch.risk === "destructive";

  async function decide(decision: "approve" | "reject", choice?: number) {
    setBusy(decision);
    setError(null);
    try {
      const res = await fetch(`/api/runs/${encodeURIComponent(id)}/approve`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(
          decision === "approve" && typeof choice === "number"
            ? { decision, choice }
            : { decision },
        ),
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
    // A destructive choice (single patch or selected option) needs a second
    // confirm: arm on the first click, send on the second. Everything else sends
    // immediately. In choice mode the selected option index rides along.
    if (destructive && !armed) {
      setArmed(true);
      return;
    }
    void decide("approve", options ? selected : undefined);
  }

  // Picking a different option resets any armed destructive confirm, so a confirm
  // armed for one option can never be sent against another.
  function onSelect(index: number) {
    setSelected(index);
    setArmed(false);
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
          {options
            ? "The diagnosis was ambiguous, so Contig is holding the run until you choose a fix. Nothing is applied without your say."
            : "A safe fix was not available, so Contig is holding the run until you approve or reject this repair. Nothing risky is applied without your say."}
        </p>

        {/* The diagnosis this decision answers. */}
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

        {options ? (
          // Choice mode: the ranked fixes as a single-select list, best first. Each
          // option is a button so it is keyboard reachable; aria-pressed marks the
          // selection. Approve sends the selected index.
          <fieldset
            className="space-y-2"
            aria-label="Choose a fix"
          >
            {options.map((option: ApprovalOption, rank: number) => {
              const isSelected = option.index === selected;
              return (
                <button
                  key={option.index}
                  type="button"
                  aria-pressed={isSelected}
                  onClick={() => onSelect(option.index)}
                  disabled={busy !== null}
                  className={cn(
                    "w-full space-y-2 rounded-lg px-3 py-2.5 text-left ring-1 transition-colors focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none disabled:pointer-events-none disabled:opacity-60",
                    isSelected
                      ? "bg-primary/5 ring-primary/40"
                      : "ring-foreground/10 hover:bg-muted/50",
                  )}
                >
                  <div className="flex flex-wrap items-center gap-2">
                    {isSelected ? (
                      <Check
                        className="size-4 text-primary"
                        aria-hidden="true"
                      />
                    ) : (
                      <span className="text-xs text-muted-foreground tabular-nums">
                        {rank + 1}
                      </span>
                    )}
                    <span className="font-mono text-sm font-medium">
                      {option.kind}
                    </span>
                    <Badge
                      variant={riskVariant(option.risk)}
                      className="font-medium"
                    >
                      {option.risk.replace(/_/g, " ")}
                    </Badge>
                  </div>
                  <p className="text-sm text-muted-foreground">
                    {option.rationale}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    Expected signal: {option.expected_signal}
                  </p>
                </button>
              );
            })}
          </fieldset>
        ) : (
          // Single mode: the one proposed patch (kind, risk, rationale).
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
        )}

        {destructive ? (
          <p className="flex items-start gap-2 text-sm text-destructive">
            <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
            <span>
              {options
                ? "The selected fix is marked destructive. Approving it can discard work or data, so it asks for a second confirm."
                : "This patch is marked destructive. Approving it can discard work or data, so it asks for a second confirm."}
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
            {destructive && armed
              ? "Confirm destructive approve"
              : options
                ? "Approve selected"
                : "Approve"}
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
