"use client";

// Two labeled selects for choosing the run ids to compare, plus a Compare button
// that navigates to /runs/compare?a=<id>&b=<id>. Kept deliberately simple and
// accessible: native selects (so keyboard and screen reader behavior is free) and
// a disabled Compare until both ids are chosen. The run id list is passed in from
// the server page so this component never touches the data layer.
import { useState } from "react";
import { useRouter } from "next/navigation";
import { GitCompareArrows } from "lucide-react";

import { Button } from "@/components/ui/button";

const SELECT_CLASS =
  "h-9 w-full rounded-lg border border-input bg-background px-2.5 text-sm text-foreground shadow-xs transition-colors focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none disabled:cursor-not-allowed disabled:opacity-50";

export function RunPicker({
  runIds,
  initialA,
  initialB,
}: {
  runIds: string[];
  initialA?: string;
  initialB?: string;
}) {
  const router = useRouter();
  const [a, setA] = useState(initialA ?? "");
  const [b, setB] = useState(initialB ?? "");

  const canCompare = a.length > 0 && b.length > 0;

  function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!canCompare) return;
    router.push(`/runs/compare?a=${encodeURIComponent(a)}&b=${encodeURIComponent(b)}`);
  }

  if (runIds.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        No runs are available to compare yet. Produce at least two run bundles,
        then return here.
      </p>
    );
  }

  return (
    <form
      onSubmit={onSubmit}
      className="flex flex-col gap-4 sm:flex-row sm:items-end"
    >
      <div className="flex-1 space-y-1.5">
        <label htmlFor="compare-a" className="text-sm font-medium text-foreground">
          Run A (baseline)
        </label>
        <select
          id="compare-a"
          value={a}
          onChange={(e) => setA(e.target.value)}
          className={SELECT_CLASS}
        >
          <option value="">Select a run</option>
          {runIds.map((id) => (
            <option key={id} value={id}>
              {id}
            </option>
          ))}
        </select>
      </div>

      <div className="flex-1 space-y-1.5">
        <label htmlFor="compare-b" className="text-sm font-medium text-foreground">
          Run B (comparison)
        </label>
        <select
          id="compare-b"
          value={b}
          onChange={(e) => setB(e.target.value)}
          className={SELECT_CLASS}
        >
          <option value="">Select a run</option>
          {runIds.map((id) => (
            <option key={id} value={id}>
              {id}
            </option>
          ))}
        </select>
      </div>

      <Button type="submit" size="lg" disabled={!canCompare} className="gap-2 sm:self-end">
        <GitCompareArrows className="size-4" aria-hidden="true" />
        Compare
      </Button>
    </form>
  );
}
