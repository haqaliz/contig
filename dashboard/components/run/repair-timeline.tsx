// The self-heal chain: a vertical timeline of repair attempts. This is the moat
// surface, so it shows the full reasoning at each attempt: the diagnosis (failure
// class, root cause, confidence, evidence), the proposed patch (or "no automatic
// patch"), and the outcome. The detector logic lives in Python, this only renders
// what it recorded.
import { CheckCircle2, HelpCircle, PauseCircle } from "lucide-react";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { RepairStep } from "@/lib/types";

// Friendly labels for the engine's machine failure classes.
const FAILURE_LABELS: Record<string, string> = {
  oom: "Out of memory",
  tool_crash: "Tool crashed",
  reference: "Reference / input problem",
  reference_mismatch: "Reference mismatch",
  missing_input: "Missing input",
  unknown: "Unknown failure",
};

function failureLabel(failureClass: string): string {
  return (
    FAILURE_LABELS[failureClass] ??
    failureClass.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())
  );
}

// Outcome -> presentation (icon, label, color). Color is never the only signal:
// every outcome carries an icon and text.
const OUTCOME_META: Record<
  string,
  { label: string; icon: typeof CheckCircle2; className: string }
> = {
  patched_and_retried: {
    label: "Patched and retried",
    icon: CheckCircle2,
    className:
      "border-emerald-300 bg-emerald-50 text-emerald-800 dark:border-emerald-800 dark:bg-emerald-950 dark:text-emerald-300",
  },
  stopped_for_confirmation: {
    label: "Stopped for confirmation",
    icon: PauseCircle,
    className:
      "border-amber-300 bg-amber-50 text-amber-900 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-300",
  },
  gave_up: {
    label: "Gave up",
    icon: HelpCircle,
    className:
      "border-slate-300 bg-slate-50 text-slate-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300",
  },
};

function OutcomeBadge({ outcome }: { outcome: string }) {
  const meta = OUTCOME_META[outcome] ?? {
    label: outcome,
    icon: HelpCircle,
    className: OUTCOME_META.gave_up.className,
  };
  const Icon = meta.icon;
  return (
    <Badge variant="outline" className={cn("gap-1 font-medium", meta.className)}>
      <Icon className="size-3.5" aria-hidden="true" />
      <span>{meta.label}</span>
    </Badge>
  );
}

// Risk gets a subtle visual weight: "safe" is calm, anything else stands out.
function RiskBadge({ risk }: { risk: string }) {
  const safe = risk.toLowerCase() === "safe";
  return (
    <Badge
      variant="outline"
      className={cn(
        "font-medium",
        safe
          ? "border-emerald-300 bg-emerald-50 text-emerald-800 dark:border-emerald-800 dark:bg-emerald-950 dark:text-emerald-300"
          : "border-amber-300 bg-amber-50 text-amber-900 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-300",
      )}
    >
      risk: {risk}
    </Badge>
  );
}

function StepCard({ step }: { step: RepairStep }) {
  const { diagnosis, patch } = step;
  const confidencePct = Math.round(diagnosis.confidence * 100);

  return (
    <li className="relative pl-8">
      {/* timeline rail + node */}
      <span
        className="absolute top-1.5 left-2.5 size-3 -translate-x-1/2 rounded-full bg-foreground/70 ring-4 ring-background"
        aria-hidden="true"
      />
      <div className="space-y-3 rounded-lg ring-1 ring-foreground/10 p-4">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm font-medium">Attempt {step.attempt}</span>
          <OutcomeBadge outcome={step.outcome} />
        </div>

        {/* Diagnosis */}
        <div>
          <h4 className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
            Diagnosis
          </h4>
          <p className="text-sm">
            <span className="font-medium">{failureLabel(diagnosis.failure_class)}</span>
            <span className="text-muted-foreground">
              {" "}
              ({confidencePct}% confidence)
            </span>
          </p>
          <p className="text-sm text-muted-foreground">{diagnosis.root_cause}</p>
          {diagnosis.evidence.length > 0 && (
            <ul className="mt-1 space-y-0.5">
              {diagnosis.evidence.map((line, i) => (
                <li
                  key={i}
                  className="rounded bg-muted/60 px-2 py-1 font-mono text-xs whitespace-pre-wrap break-words"
                >
                  {line}
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* Patch */}
        <div>
          <h4 className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
            Patch
          </h4>
          {patch ? (
            <div className="space-y-1.5">
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant="secondary">{patch.kind}</Badge>
                <RiskBadge risk={patch.risk} />
              </div>
              <p className="text-sm">{patch.rationale}</p>
              <pre className="overflow-x-auto rounded bg-muted/60 px-2 py-1.5 font-mono text-xs">
                {JSON.stringify(patch.operation, null, 2)}
              </pre>
              <p className="text-xs text-muted-foreground">
                Expected signal: {patch.expected_signal}
              </p>
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">No automatic patch.</p>
          )}
        </div>
      </div>
    </li>
  );
}

export function RepairTimeline({ history }: { history: RepairStep[] }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Self-heal</CardTitle>
        <CardDescription>
          The bounded detect, diagnose, patch, re-run loop.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {history.length === 0 ? (
          <p className="text-sm text-muted-foreground">No repairs were needed.</p>
        ) : (
          <ol className="relative space-y-4 before:absolute before:top-2 before:bottom-2 before:left-2.5 before:w-px before:bg-border">
            {history.map((step) => (
              <StepCard key={step.attempt} step={step} />
            ))}
          </ol>
        )}
      </CardContent>
    </Card>
  );
}
