"use client";

// Resources and cost for a finished run (PRD contracts A, B). Per-task duration
// and peak memory come from run_record.json resource_usage; the total cost comes
// from `contig cost <id> --json` (the cost model lives in the engine, not here).
//
// The card opens with the cost at the default rates (0, since local compute is
// free, so the default total is zero). The user may enter a cpu and memory rate
// to get a real estimate; entering rates re-fetches the cost from the engine via
// /api/runs/[id]/cost so the math stays in one place.
import { useState } from "react";
import { Cpu, Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { CostReport, TaskResource } from "@/lib/types";

// Seconds to a compact "Xh Ym Zs" (omitting zero leading units), or "0s".
function formatDuration(sec: number): string {
  if (!Number.isFinite(sec) || sec <= 0) return "0s";
  const total = Math.round(sec);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  const parts: string[] = [];
  if (h > 0) parts.push(`${h}h`);
  if (m > 0) parts.push(`${m}m`);
  if (s > 0 || parts.length === 0) parts.push(`${s}s`);
  return parts.join(" ");
}

// MB to "X.Y GB" once it crosses a gigabyte, else "Z MB". Keeps the table tidy.
function formatMemory(mb: number): string {
  if (!Number.isFinite(mb) || mb <= 0) return "0 MB";
  if (mb >= 1024) return `${(mb / 1024).toFixed(1)} GB`;
  return `${Math.round(mb)} MB`;
}

// A cost as currency, to four decimals so a fraction of a cent still shows.
function formatCost(value: number, currency: string): string {
  if (!Number.isFinite(value)) return `0 ${currency}`;
  return `${value.toFixed(4)} ${currency}`;
}

export function ResourceCostCard({
  id,
  resourceUsage,
  initialCost,
}: {
  id: string;
  resourceUsage: TaskResource[];
  // The cost at the default rates, computed server-side, or null if the engine
  // could not produce one (the card then shows resources without a total).
  initialCost: CostReport | null;
}) {
  const [cost, setCost] = useState<CostReport | null>(initialCost);
  const [cpuRate, setCpuRate] = useState("");
  const [memRate, setMemRate] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const hasUsage = resourceUsage.length > 0;

  async function recompute() {
    setLoading(true);
    setError(null);
    try {
      const qs = new URLSearchParams();
      if (cpuRate.trim()) qs.set("cpuHour", cpuRate.trim());
      if (memRate.trim()) qs.set("memGbHour", memRate.trim());
      const res = await fetch(
        `/api/runs/${encodeURIComponent(id)}/cost?${qs.toString()}`,
      );
      if (res.ok) {
        setCost((await res.json()) as CostReport);
      } else {
        const data = (await res.json().catch(() => ({}))) as { error?: string };
        setError(data.error ?? "Could not compute the cost.");
      }
    } catch {
      setError("Could not compute the cost.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <Card aria-labelledby="resources-title">
      <CardHeader className="gap-3 border-b pb-4">
        <CardTitle
          id="resources-title"
          className="flex flex-wrap items-center gap-3 text-lg"
        >
          <Cpu className="size-4 text-muted-foreground" aria-hidden="true" />
          Resources and cost
          {cost ? (
            <span className="ml-auto font-mono text-base font-medium">
              {formatCost(cost.total, cost.currency)}
            </span>
          ) : null}
        </CardTitle>
        <CardDescription>
          {hasUsage
            ? "Per-task wall-clock duration and peak memory, recorded from the run's trace. The total applies the rates below (the default rates are zero, since local compute is free)."
            : "This run recorded no per-task resource usage, so there is nothing to cost. Newer runs capture duration, peak memory, and cpu from the trace."}
        </CardDescription>
      </CardHeader>

      <CardContent className="space-y-5 pt-5">
        {hasUsage ? (
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Task</TableHead>
                  <TableHead className="text-right">Duration</TableHead>
                  <TableHead className="text-right">Peak memory</TableHead>
                  <TableHead className="text-right">CPU</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {resourceUsage.map((t, i) => (
                  <TableRow key={`${t.process}-${t.name ?? i}`}>
                    <TableCell className="font-mono text-xs break-all">
                      {t.name ?? t.process}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {formatDuration(t.realtime_sec)}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {formatMemory(t.peak_rss_mb)}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {Math.round(t.pct_cpu)}%
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        ) : null}

        {hasUsage ? (
          <div className="flex flex-col gap-3 border-t pt-4 sm:flex-row sm:items-end">
            <div className="flex flex-col gap-1.5">
              <label
                htmlFor="cpu-rate"
                className="text-xs font-medium text-muted-foreground"
              >
                CPU rate (per core hour)
              </label>
              <Input
                id="cpu-rate"
                inputMode="decimal"
                placeholder="0.00"
                value={cpuRate}
                onChange={(e) => setCpuRate(e.target.value)}
                className="w-40"
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <label
                htmlFor="mem-rate"
                className="text-xs font-medium text-muted-foreground"
              >
                Memory rate (per GB hour)
              </label>
              <Input
                id="mem-rate"
                inputMode="decimal"
                placeholder="0.00"
                value={memRate}
                onChange={(e) => setMemRate(e.target.value)}
                className="w-40"
              />
            </div>
            <Button
              type="button"
              variant="outline"
              onClick={() => void recompute()}
              disabled={loading}
            >
              {loading ? (
                <Loader2 className="size-4 animate-spin" aria-hidden="true" />
              ) : null}
              Apply rates
            </Button>
            {error ? (
              <p role="alert" className="text-sm text-destructive">
                {error}
              </p>
            ) : null}
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}
