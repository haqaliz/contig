"use client";

// The header bell and its activity panel (PRD contract A). It lists recent run
// lifecycle events read from <runsDir>/notifications.jsonl (newest first). The
// events are fetched on the server and passed in, so this island never touches
// the data layer. An awaiting_approval event links to its run (/runs/<id>) so a
// paused run can be resolved straight from the panel. A dot on the bell flags
// that at least one run is awaiting approval, the only event that needs the user.
import {
  Bell,
  CheckCircle2,
  XCircle,
  Ban,
  PauseCircle,
  ArrowRight,
  type LucideIcon,
} from "lucide-react";

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Button } from "@/components/ui/button";
import { ButtonLink } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { NotificationEvent, NotificationKind } from "@/lib/types";

const KIND: Record<
  NotificationKind,
  { label: string; icon: LucideIcon; className: string }
> = {
  finished: {
    label: "Finished",
    icon: CheckCircle2,
    className: "text-emerald-600 dark:text-emerald-400",
  },
  failed: {
    label: "Failed",
    icon: XCircle,
    className: "text-red-600 dark:text-red-400",
  },
  cancelled: {
    label: "Cancelled",
    icon: Ban,
    className: "text-slate-500 dark:text-slate-400",
  },
  awaiting_approval: {
    label: "Awaiting approval",
    icon: PauseCircle,
    className: "text-amber-600 dark:text-amber-400",
  },
};

/** Format an ISO timestamp as a short, locale-neutral wall-clock string. */
function shortTime(ts: string): string {
  const ms = Date.parse(ts);
  if (Number.isNaN(ms)) return ts;
  // A fixed UTC format keeps the server and client render identical (no
  // hydration mismatch from a per-client locale).
  return new Date(ms).toISOString().replace("T", " ").slice(0, 16) + " UTC";
}

export function NotificationBell({ events }: { events: NotificationEvent[] }) {
  const awaiting = events.some((e) => e.kind === "awaiting_approval");

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        render={
          <Button
            variant="ghost"
            size="icon"
            aria-label={
              awaiting
                ? "Recent activity, a run is awaiting approval"
                : "Recent activity"
            }
            className="relative"
          >
            <Bell className="size-4" aria-hidden="true" />
            {awaiting ? (
              <span
                aria-hidden="true"
                className="absolute right-1.5 top-1.5 size-2 rounded-full bg-amber-500 ring-2 ring-background"
              />
            ) : null}
          </Button>
        }
      />
      <DropdownMenuContent
        align="end"
        className="w-(--anchor-width) min-w-80 max-w-96 p-0"
      >
        <div className="border-b px-3 py-2">
          <p className="text-sm font-medium">Recent activity</p>
          <p className="text-xs text-muted-foreground">
            Run lifecycle events, newest first.
          </p>
        </div>
        {events.length === 0 ? (
          <p className="px-3 py-6 text-center text-sm text-muted-foreground">
            No activity yet. Run events appear here as runs finish, fail, or pause
            for approval.
          </p>
        ) : (
          <ul className="max-h-96 divide-y overflow-y-auto" data-testid="notification-list">
            {events.map((e, i) => {
              const cfg = KIND[e.kind];
              const Icon = cfg.icon;
              const isApproval = e.kind === "awaiting_approval";
              return (
                <li key={`${e.run_id}-${e.ts}-${i}`} className="px-3 py-2.5">
                  <div className="flex items-start gap-2.5">
                    <Icon
                      className={cn("mt-0.5 size-4 shrink-0", cfg.className)}
                      aria-hidden="true"
                    />
                    <div className="min-w-0 flex-1">
                      <p className="flex items-center gap-2 text-sm">
                        <span className="font-medium">{cfg.label}</span>
                        <span className="text-xs text-muted-foreground tabular-nums">
                          {shortTime(e.ts)}
                        </span>
                      </p>
                      <p className="truncate font-mono text-xs text-muted-foreground">
                        {e.run_id}
                      </p>
                      <p className="mt-0.5 text-sm text-foreground">{e.message}</p>
                      {isApproval ? (
                        <ButtonLink
                          href={`/runs/${encodeURIComponent(e.run_id)}`}
                          variant="outline"
                          size="xs"
                          className="mt-2 gap-1"
                        >
                          Review and approve
                          <ArrowRight className="size-3" aria-hidden="true" />
                        </ButtonLink>
                      ) : null}
                    </div>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
