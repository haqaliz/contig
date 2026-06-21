// Shared, accessible status pill for verdicts and QC statuses. Color is never the
// sole signal: every badge carries an icon and a text label (accessibility
// baseline), so it reads correctly for colorblind users and screen readers.
import {
  CheckCircle2,
  AlertTriangle,
  XCircle,
  HelpCircle,
  type LucideIcon,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { QCStatus, Verdict } from "@/lib/types";

type Status = Verdict | QCStatus;

const MAP: Record<Status, { label: string; icon: LucideIcon; className: string }> = {
  pass: {
    label: "Pass",
    icon: CheckCircle2,
    className: "border-emerald-300 bg-emerald-50 text-emerald-800 dark:border-emerald-800 dark:bg-emerald-950 dark:text-emerald-300",
  },
  warn: {
    label: "Warn",
    icon: AlertTriangle,
    className: "border-amber-300 bg-amber-50 text-amber-900 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-300",
  },
  fail: {
    label: "Fail",
    icon: XCircle,
    className: "border-red-300 bg-red-50 text-red-800 dark:border-red-900 dark:bg-red-950 dark:text-red-300",
  },
  unverified: {
    label: "Unverified",
    icon: HelpCircle,
    className: "border-slate-300 bg-slate-50 text-slate-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300",
  },
};

export function StatusBadge({
  status,
  className,
  size = "sm",
}: {
  status: Status;
  className?: string;
  size?: "sm" | "lg";
}) {
  const cfg = MAP[status] ?? MAP.unverified;
  const Icon = cfg.icon;
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
      <span>{cfg.label}</span>
    </Badge>
  );
}
