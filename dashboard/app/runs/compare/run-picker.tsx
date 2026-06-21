"use client";

// Two labeled selects for choosing the run ids to compare, plus a Compare button
// that navigates to /runs/compare?a=<id>&b=<id>. Uses the shadcn Select. Compare
// stays disabled until both ids are chosen. The run id list is passed in from the
// server page, so this component never touches the data layer.
import { useState } from "react";
import { useRouter } from "next/navigation";
import { GitCompareArrows } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

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

  // A run can never be compared against itself, so the id picked on one side is
  // removed from the other side's options. The current selection is always kept
  // in its own list so the trigger can still display it.
  const optionsForA = runIds.filter((id) => id !== b);
  const optionsForB = runIds.filter((id) => id !== a);

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
    <form onSubmit={onSubmit} className="flex flex-col gap-4 sm:flex-row sm:items-end">
      <div className="flex-1 space-y-1.5">
        <label id="compare-a-label" className="text-sm font-medium text-foreground">
          Run A (baseline)
        </label>
        <Select value={a} onValueChange={(v) => setA(v as string)}>
          <SelectTrigger aria-labelledby="compare-a-label" className="w-full">
            <SelectValue placeholder="Select a run" />
          </SelectTrigger>
          <SelectContent>
            {optionsForA.map((id) => (
              <SelectItem key={id} value={id}>
                {id}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="flex-1 space-y-1.5">
        <label id="compare-b-label" className="text-sm font-medium text-foreground">
          Run B (comparison)
        </label>
        <Select value={b} onValueChange={(v) => setB(v as string)}>
          <SelectTrigger aria-labelledby="compare-b-label" className="w-full">
            <SelectValue placeholder="Select a run" />
          </SelectTrigger>
          <SelectContent>
            {optionsForB.map((id) => (
              <SelectItem key={id} value={id}>
                {id}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <Button type="submit" size="lg" disabled={!canCompare} className="gap-2 sm:self-end">
        <GitCompareArrows className="size-4" aria-hidden="true" />
        Compare
      </Button>
    </form>
  );
}
