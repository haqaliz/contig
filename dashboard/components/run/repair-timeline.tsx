// The self-heal chain: a vertical timeline of repair attempts. This is the moat
// surface, so it shows the full reasoning at each attempt: the diagnosis (failure
// class, root cause, confidence, evidence), the proposed patch (or "no automatic
// patch"), and the outcome. The detector logic lives in Python, this only renders
// what it recorded.
import { CheckCircle2, Flag, Hand, HelpCircle, RotateCcw } from "lucide-react";

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
  qc_anomaly: "QC anomaly",
  unknown: "Unknown failure",
};

function failureLabel(failureClass: string): string {
  return (
    FAILURE_LABELS[failureClass] ??
    failureClass.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())
  );
}

// Three visual families, because there are three materially different things that
// can happen to a proposed patch, and conflating them is how this surface used to
// overclaim in both directions.
//
//   APPLIED   -- the patch was enacted and the loop retried (RepairStep.patch_applied).
//   DECLINED  -- a human said no, or said nothing in time. The ENGINE DID NOT FAIL.
//                This must never share GAVE_UP's styling; that is asserted, as a
//                negative class comparison, in e2e/repair-truthfulness.spec.ts.
//   GAVE_UP   -- the engine ran out of road and says so: budget, ceiling, or a
//                repair helper that could not resolve or build what it needed.
//
// One outcome sits outside all three: qc_verdict_flagged is a finding on a run
// whose tasks all succeeded -- nothing failed and nothing was patched -- so it
// keeps its own amber. That amber is now unique: the previous holder of the token,
// stopped_for_confirmation, was emitted NOWHERE in src/ and has been deleted.
const APPLIED =
  "border-emerald-300 bg-emerald-50 text-emerald-800 dark:border-emerald-800 dark:bg-emerald-950 dark:text-emerald-300";
const DECLINED =
  "border-sky-300 bg-sky-50 text-sky-800 dark:border-sky-800 dark:bg-sky-950 dark:text-sky-300";
const GAVE_UP =
  "border-slate-300 bg-slate-50 text-slate-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300";
const FLAGGED =
  "border-amber-300 bg-amber-50 text-amber-900 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-300";

// Outcome -> presentation (icon, label, color). Color is never the only signal:
// every outcome carries an icon and text. Every literal the engine emits is mapped
// here -- 15 from self_heal.py, 3 from verification/reproduce.py (which shares the
// RepairStep type through ReproduceRecord.repair_history). The fallback below is
// kept as a defensive path, but no known literal should reach it.
export const OUTCOME_META: Record<
  string,
  { label: string; icon: typeof CheckCircle2; className: string }
> = {
  // --- applied: enacted, and the loop went on to retry -------------------------
  patched_and_retried: {
    label: "Patched and retried",
    icon: CheckCircle2,
    className: APPLIED,
  },
  approved_and_retried: {
    label: "You approved this fix; retried",
    icon: CheckCircle2,
    className: APPLIED,
  },
  chose_and_retried: {
    label: "You chose this fix; retried",
    icon: CheckCircle2,
    className: APPLIED,
  },
  built_index_and_retried: {
    label: "Built the index and retried",
    icon: CheckCircle2,
    className: APPLIED,
  },
  recompressed_reference_and_retried: {
    label: "Recompressed the reference and retried",
    icon: CheckCircle2,
    className: APPLIED,
  },
  installed_and_retried: {
    label: "Installed the dependency and retried",
    icon: CheckCircle2,
    className: APPLIED,
  },
  // Applied, not successful: the install ran, so the fix WAS enacted, and the
  // retry then failed anyway. It belongs to this family because the family means
  // "enacted", not "worked" -- the label carries the bad news, and the icon
  // separates it from its siblings without splintering the family's colour.
  retry_failed: {
    label: "Installed, but the retry still failed",
    icon: RotateCcw,
    className: APPLIED,
  },

  // --- the human declined: a decision, not a failure ---------------------------
  rejected_by_user: {
    label: "You rejected this fix",
    icon: Hand,
    className: DECLINED,
  },
  approval_timed_out: {
    label: "Waited for your approval; timed out",
    icon: Hand,
    className: DECLINED,
  },
  invalid_choice_rejected: {
    label: "That choice was not one of the options",
    icon: Hand,
    className: DECLINED,
  },

  // --- the engine gave up, honestly --------------------------------------------
  gave_up: {
    label: "Gave up",
    icon: HelpCircle,
    className: GAVE_UP,
  },
  gave_up_at_ceiling: {
    label: "Gave up: already at the resource ceiling",
    icon: HelpCircle,
    className: GAVE_UP,
  },
  index_build_failed: {
    label: "Gave up: the index build failed",
    icon: HelpCircle,
    className: GAVE_UP,
  },
  index_unresolvable: {
    label: "Gave up: could not resolve which index to build",
    icon: HelpCircle,
    className: GAVE_UP,
  },
  reference_recompress_failed: {
    label: "Gave up: recompressing the reference failed",
    icon: HelpCircle,
    className: GAVE_UP,
  },
  reference_recompress_unresolvable: {
    label: "Gave up: could not resolve which reference to recompress",
    icon: HelpCircle,
    className: GAVE_UP,
  },
  install_failed: {
    label: "Gave up: the dependency install failed",
    icon: HelpCircle,
    className: GAVE_UP,
  },

  // --- a finding on a green run: neither applied, declined, nor a give-up -------
  qc_verdict_flagged: {
    label: "QC verdict flagged",
    icon: Flag,
    className: FLAGGED,
  },
};

function OutcomeBadge({ outcome }: { outcome: string }) {
  // Defensive only: every literal the engine emits today is mapped above. If one
  // reaches here it is genuinely unknown to this build, so the honest rendering is
  // the raw literal in give-up styling rather than a guess at which family it is.
  const meta = OUTCOME_META[outcome] ?? {
    label: outcome,
    icon: HelpCircle,
    className: GAVE_UP,
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
          The bounded detect, diagnose, patch, re-run loop. Not every diagnosis
          produces a patch.
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
