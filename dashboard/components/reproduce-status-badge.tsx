// Shared, accessible status pill for third-party `contig reproduce` claim
// statuses (C8). Sibling of status-badge.tsx, which keeps the first-party
// pass/warn/fail/unverified map untouched. The four lowercase record literals
// map 1:1 onto the existing palette semantics: reproduced (emerald,
// CheckCircle2, mirror pass), within_tolerance (amber, AlertTriangle, mirror
// warn), diverged (red, XCircle, mirror fail), unverified (slate, HelpCircle,
// mirror unverified). Color is never the sole signal: every badge carries an
// icon and a text label.
//
// Two forward-compat rules:
//  - An UNKNOWN status literal renders a neutral "Unknown" pill, never a crash
//    (a bundle written by a newer contig than this dashboard).
//  - The derived "did_not_complete" overall (non-zero exit_code) renders its
//    own red/XCircle pill -- "Did not complete (exit N)" -- and is never shown
//    as a claim-status badge.
import {
  AlertTriangle,
  CheckCircle2,
  HelpCircle,
  XCircle,
  type LucideIcon,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

const MAP: Record<string, { label: string; icon: LucideIcon; className: string }> = {
  reproduced: {
    label: "Reproduced",
    icon: CheckCircle2,
    className: "border-emerald-300 bg-emerald-50 text-emerald-800 dark:border-emerald-800 dark:bg-emerald-950 dark:text-emerald-300",
  },
  within_tolerance: {
    label: "Within tolerance",
    icon: AlertTriangle,
    className: "border-amber-300 bg-amber-50 text-amber-900 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-300",
  },
  diverged: {
    label: "Diverged",
    icon: XCircle,
    className: "border-red-300 bg-red-50 text-red-800 dark:border-red-900 dark:bg-red-950 dark:text-red-300",
  },
  unverified: {
    label: "Unverified",
    icon: HelpCircle,
    className: "border-slate-300 bg-slate-50 text-slate-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300",
  },
};

const UNKNOWN = {
  label: "Unknown",
  icon: HelpCircle,
  className: "border-border text-muted-foreground",
};

const DID_NOT_COMPLETE = {
  label: "Did not complete",
  icon: XCircle,
  className: "border-red-300 bg-red-50 text-red-800 dark:border-red-900 dark:bg-red-950 dark:text-red-300",
};

export function ReproduceStatusBadge({
  status,
  exitCode,
  className,
  size = "sm",
}: {
  status: string;
  // Only meaningful for status "did_not_complete": renders the exit code in the
  // label (e.g. "Did not complete (exit 2)").
  exitCode?: number;
  className?: string;
  size?: "sm" | "lg";
}) {
  const isDidNotComplete = status === "did_not_complete";
  const cfg = isDidNotComplete ? DID_NOT_COMPLETE : (MAP[status] ?? UNKNOWN);
  const Icon = cfg.icon;
  const label = isDidNotComplete
    ? exitCode !== undefined
      ? `Did not complete (exit ${exitCode})`
      : cfg.label
    : cfg.label;
  return (
    <Badge
      variant="outline"
      className={cn(
        "gap-1 font-medium",
        size === "lg" && "px-3 py-1 text-sm",
        cfg.className,
        className,
      )}
    >
      <Icon className={cn(size === "lg" ? "size-4" : "size-3.5")} aria-hidden="true" />
      <span>{label}</span>
    </Badge>
  );
}