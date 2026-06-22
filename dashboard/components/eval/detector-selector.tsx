"use client";

// The detector picker on /eval (PRD contract C). The failure detector is
// pluggable: the engine registers several detectors behind one interface, and
// eval-detector can score any of them. This select drives ?detector=<name>, and
// the server page re-fetches getDetectorEval for the chosen detector so the
// existing accuracy / per-class view renders that detector's report. "rules" is
// the default. The known names are passed in from the server, so this island
// never hard-codes the registry.
import { useRouter } from "next/navigation";

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

// Human labels for the registered detectors. A name not listed here falls back
// to its raw key, so adding a detector never breaks the selector.
const LABELS: Record<string, string> = {
  rules: "Rules (default)",
  "rules-strict": "Rules, strict",
};

export function DetectorSelector({
  detectors,
  selected,
}: {
  detectors: readonly string[];
  selected: string;
}) {
  const router = useRouter();

  function onChange(value: string) {
    if (value === selected) return;
    // "rules" is the default, so a clean URL drops the query for it.
    router.push(value === "rules" ? "/eval" : `/eval?detector=${encodeURIComponent(value)}`);
  }

  return (
    <div className="flex flex-col gap-1.5 sm:flex-row sm:items-center sm:gap-3">
      <label id="detector-label" className="text-sm font-medium text-foreground">
        Detector
      </label>
      <Select value={selected} onValueChange={(v) => onChange(v as string)}>
        <SelectTrigger aria-labelledby="detector-label" className="w-full sm:w-64">
          {/* Render the friendly label in the trigger. Base UI shows the raw
              value otherwise, since the items mount lazily in a portal. */}
          <SelectValue>
            {(value) => LABELS[value as string] ?? (value as string)}
          </SelectValue>
        </SelectTrigger>
        <SelectContent>
          {detectors.map((name) => (
            <SelectItem key={name} value={name}>
              {LABELS[name] ?? name}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}
