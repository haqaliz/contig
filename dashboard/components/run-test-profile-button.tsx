"use client";

// Launch the bundled test-profile run (no inputs) from the dashboard. POSTs to
// the dispatch route, then navigates to the new run, which shows "in progress"
// until the verdict bundle appears. One run at a time (a 409 is surfaced inline).
import { useState } from "react";
import { useRouter } from "next/navigation";
import { Loader2, Play } from "lucide-react";

import { Button } from "@/components/ui/button";

export function RunTestProfileButton() {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function start() {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch("/api/runs/dispatch", { method: "POST" });
      const data = (await res.json()) as { run_id?: string; error?: string };
      if (res.ok && data.run_id) {
        router.push(`/runs/${data.run_id}`);
        return;
      }
      setError(data.error ?? "Could not start the run.");
    } catch {
      setError("Could not start the run.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col items-start gap-1 sm:items-end">
      <Button type="button" size="sm" onClick={start} disabled={busy}>
        {busy ? (
          <Loader2 className="size-4 animate-spin" aria-hidden="true" />
        ) : (
          <Play className="size-4" aria-hidden="true" />
        )}
        Run test profile
      </Button>
      {error ? (
        <p role="alert" className="text-xs text-destructive">
          {error}
        </p>
      ) : null}
    </div>
  );
}
