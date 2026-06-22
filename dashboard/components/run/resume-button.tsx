"use client";

// The Resume control on a cancelled or interrupted run. It POSTs to
// /api/runs/[id]/resume, which shells `contig resume <id>` to re-run the SAME run
// id in the same run dir with Nextflow -resume (cached tasks are reused). On
// success the run goes back to "running", so it refreshes into the live view. The
// dashboard never spawns the process itself.
import { useState } from "react";
import { useRouter } from "next/navigation";
import { Loader2, Play } from "lucide-react";

import { Button } from "@/components/ui/button";

export function ResumeButton({
  id,
  size = "default",
}: {
  id: string;
  size?: "default" | "sm";
}) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function resume() {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`/api/runs/${encodeURIComponent(id)}/resume`, {
        method: "POST",
      });
      if (res.ok) {
        router.refresh();
        return;
      }
      const data = (await res.json().catch(() => ({}))) as { error?: string };
      setError(data.error ?? "Could not resume the run.");
      setBusy(false);
    } catch {
      setError("Could not resume the run.");
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col items-center gap-2">
      <Button
        type="button"
        size={size}
        onClick={() => void resume()}
        disabled={busy}
      >
        {busy ? (
          <Loader2 className="size-4 animate-spin" aria-hidden="true" />
        ) : (
          <Play className="size-4" aria-hidden="true" />
        )}
        Resume run
      </Button>
      {error ? (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      ) : null}
    </div>
  );
}
