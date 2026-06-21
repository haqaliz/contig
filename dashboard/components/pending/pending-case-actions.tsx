"use client";

// Curate a pending case: confirm the provisional label, or correct it, then
// promote into the golden corpus. The write goes through the CLI (the corpus
// logic stays in Python). On success the case leaves pending, so we refresh.
import { useState } from "react";
import { useRouter } from "next/navigation";
import { Check, ChevronDown, Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { FAILURE_CLASSES } from "@/lib/derive";

export function PendingCaseActions({
  caseId,
  provisional,
}: {
  caseId: string;
  provisional: string;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function promote(label?: string) {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch("/api/corpus/promote", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ case_id: caseId, label }),
      });
      if (res.ok) {
        router.refresh();
        return;
      }
      const data = (await res.json()) as { error?: string };
      setError(data.error ?? "Could not promote the case.");
    } catch {
      setError("Could not promote the case.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      <Button type="button" size="sm" disabled={busy} onClick={() => promote()}>
        {busy ? (
          <Loader2 className="size-4 animate-spin" aria-hidden="true" />
        ) : (
          <Check className="size-4" aria-hidden="true" />
        )}
        Confirm {provisional}
      </Button>

      <DropdownMenu>
        <DropdownMenuTrigger
          render={
            <Button type="button" size="sm" variant="outline" disabled={busy} className="gap-1" />
          }
        >
          Correct label
          <ChevronDown className="size-4 opacity-60" aria-hidden="true" />
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start" className="max-h-72 overflow-auto">
          {FAILURE_CLASSES.filter((c) => c !== provisional).map((c) => (
            <DropdownMenuItem key={c} onClick={() => promote(c)} className="font-mono text-xs">
              {c}
            </DropdownMenuItem>
          ))}
        </DropdownMenuContent>
      </DropdownMenu>

      {error ? (
        <span role="alert" className="text-xs text-destructive">
          {error}
        </span>
      ) : null}
    </div>
  );
}
