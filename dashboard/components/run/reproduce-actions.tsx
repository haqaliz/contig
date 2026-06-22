"use client";

// The reproduce actions on a run's detail page. "Reproduce exactly" POSTs to
// the reproduce API (which rebuilds the run from its launch.json with a fresh
// id) and then redirects to the compare view so the original and the new run sit
// side by side. "Edit and relaunch" links to the launch form pre-filled from
// this run's manifest (?from=<id>). Shown only when a launch manifest exists.
import { useState } from "react";
import { useRouter } from "next/navigation";
import { Loader2, Pencil, RotateCcw } from "lucide-react";

import { Button, ButtonLink } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

export function ReproduceActions({ id }: { id: string }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function reproduce() {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`/api/runs/${encodeURIComponent(id)}/reproduce`, {
        method: "POST",
      });
      const data = (await res.json()) as { run_id?: string; error?: string };
      if (res.ok && data.run_id) {
        router.push(
          `/runs/compare?a=${encodeURIComponent(id)}&b=${encodeURIComponent(
            data.run_id,
          )}`,
        );
        return;
      }
      setError(data.error ?? "Could not reproduce this run.");
    } catch {
      setError("Could not reproduce this run.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardContent className="flex flex-wrap items-center gap-3 py-5">
        <Button type="button" onClick={() => void reproduce()} disabled={busy}>
          {busy ? (
            <Loader2 className="size-4 animate-spin" aria-hidden="true" />
          ) : (
            <RotateCcw className="size-4" aria-hidden="true" />
          )}
          Reproduce exactly
        </Button>
        <ButtonLink
          variant="outline"
          href={`/runs/new?from=${encodeURIComponent(id)}`}
          aria-disabled={busy}
          tabIndex={busy ? -1 : undefined}
          className={busy ? "pointer-events-none opacity-50" : undefined}
        >
          <Pencil className="size-4" aria-hidden="true" />
          Edit and relaunch
        </ButtonLink>
        <p className="text-xs text-muted-foreground">
          Reproduce re-runs this exact configuration; edit and relaunch opens a
          pre-filled form.
        </p>
        {error ? (
          <p
            role="alert"
            className="w-full rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive"
          >
            {error}
          </p>
        ) : null}
      </CardContent>
    </Card>
  );
}
