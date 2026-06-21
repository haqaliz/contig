// Shared page header so /runs, /runs/[id], and /eval share one header rhythm:
// a title (with an optional muted count) and a description, on a consistent
// vertical scale. Keep the title element a real <h1> so each page has one
// top-level heading for accessibility and the smoke tests.
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

export function PageHeader({
  title,
  count,
  description,
  actions,
  titleClassName,
  className,
}: {
  title: ReactNode;
  count?: number;
  description?: ReactNode;
  actions?: ReactNode;
  titleClassName?: string;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between",
        className,
      )}
    >
      <div className="space-y-1.5">
        <h1
          className={cn(
            "font-heading text-2xl font-semibold tracking-tight text-foreground",
            titleClassName,
          )}
        >
          {title}
          {count !== undefined ? (
            <span className="ml-1.5 font-normal text-muted-foreground tabular-nums">
              ({count})
            </span>
          ) : null}
        </h1>
        {description ? (
          <p className="max-w-2xl text-sm text-muted-foreground">
            {description}
          </p>
        ) : null}
      </div>
      {actions ? <div className="shrink-0">{actions}</div> : null}
    </div>
  );
}
