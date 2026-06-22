"use client";

// The Cancel control on an in-flight run (running or awaiting_approval). It POSTs
// to /api/runs/[id]/cancel, which shells `contig cancel <id>` to stop the run's
// process group and write status.json state "cancelled"; on success it refreshes
// so the page re-renders into the cancelled view. The dashboard never kills a
// process itself.
import { useState } from "react";
import { useRouter } from "next/navigation";
import { Loader2, Square } from "lucide-react";

import { Button } from "@/components/ui/button";

export function CancelButton({ id }: { id: string }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function cancel() {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`/api/runs/${encodeURIComponent(id)}/cancel`, {
        method: "POST",
      });
      if (res.ok) {
        router.refresh();
        return;
      }
      const data = (await res.json().catch(() => ({}))) as { error?: string };
      setError(data.error ?? "Could not cancel the run.");
      setBusy(false);
    } catch {
      setError("Could not cancel the run.");
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-wrap items-center gap-3">
      <Button
        type="button"
        variant="outline"
        onClick={() => void cancel()}
        disabled={busy}
      >
        {busy ? (
          <Loader2 className="size-4 animate-spin" aria-hidden="true" />
        ) : (
          <Square className="size-4" aria-hidden="true" />
        )}
        Cancel run
      </Button>
      {error ? (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      ) : null}
    </div>
  );
}
