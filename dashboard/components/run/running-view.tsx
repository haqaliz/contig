"use client";

// Shown while a run is in flight (status.json says "running", no bundle yet).
// It polls the server (router.refresh) so the moment the verdict bundle lands,
// the page re-renders into the normal run detail. v1 has no per-task progress;
// that needs the engine status-stream work (a later milestone).
import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { Loader2 } from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";

export function RunningView({ startedAt }: { startedAt?: string }) {
  const router = useRouter();

  useEffect(() => {
    const t = setInterval(() => router.refresh(), 3000);
    return () => clearInterval(t);
  }, [router]);

  return (
    <Card aria-live="polite">
      <CardContent className="flex flex-col items-center gap-3 py-12 text-center">
        <Loader2 className="size-8 animate-spin text-brand" aria-hidden="true" />
        <div className="space-y-1">
          <p className="text-base font-medium">This run is in progress</p>
          <p className="text-sm text-muted-foreground">
            Contig is running the pipeline and will self-heal and verify it. The
            verdict appears here automatically when it finishes.
          </p>
          {startedAt ? (
            <p className="text-xs text-muted-foreground">
              Started {new Date(startedAt).toLocaleString()}
            </p>
          ) : null}
        </div>
      </CardContent>
    </Card>
  );
}
