"use client";

// Interactive reproduce listing: text filter (reproduce id or repo), overall
// status filter, and a default sort that floats the worst overalls to the top
// (did not complete, then diverged, within tolerance, unverified, reproduced;
// created desc as the tiebreak). All trust logic stays in the engine: we only
// read the serialized record and derive the display status client-side.
import { useMemo, useState } from "react";
import Link from "next/link";
import { ChevronDown, ListFilter } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { ReproduceStatusBadge } from "@/components/reproduce-status-badge";
import {
  claimCountsLine,
  claimStatusLabel,
  deriveReproduceOverall,
  REPRODUCE_STATUS_ORDER,
  type ReproduceOverall,
} from "@/lib/reproduce-derive";
import type { ReproduceRecord } from "@/lib/types";

// The overall-status filter buttons. "all" keeps everything; the rest match
// one derived overall (an unknown literal derives as unverified, so it falls
// under Unverified here).
const OVERALL_FILTERS: { key: ReproduceOverall | "all"; label: string }[] = [
  { key: "all", label: "All" },
  { key: "diverged", label: "Diverged" },
  { key: "within_tolerance", label: "Within tolerance" },
  { key: "unverified", label: "Unverified" },
  { key: "reproduced", label: "Reproduced" },
  { key: "did_not_complete", label: "Did not complete" },
];

// Sort rank for the default severity sort. did_not_complete is the worst
// presentation (the run never finished); the known literals use
// REPRODUCE_STATUS_ORDER; an unknown literal ranks as unverified.
function overallRank(overall: ReproduceOverall): number {
  if (overall === "did_not_complete") return -1;
  return REPRODUCE_STATUS_ORDER[overall] ?? REPRODUCE_STATUS_ORDER.unverified;
}

export function ReproduceTable({ records }: { records: ReproduceRecord[] }) {
  const [query, setQuery] = useState("");
  const [overall, setOverall] = useState<ReproduceOverall | "all">("all");

  const overallLabel =
    OVERALL_FILTERS.find((f) => f.key === overall)?.label ?? "All";

  const rows = useMemo(() => {
    const q = query.trim().toLowerCase();

    const filtered = records.filter((r) => {
      const derived = deriveReproduceOverall(r).overall;
      if (overall !== "all" && derived !== overall) return false;
      if (q.length === 0) return true;
      const repo = (r.repo || r.source_url || "").toLowerCase();
      return (
        r.reproduce_id.toLowerCase().includes(q) || repo.includes(q)
      );
    });

    // Default: worst overall first, then created desc (newest on top within
    // the same severity band).
    return [...filtered].sort((a, b) => {
      const rankDiff =
        overallRank(deriveReproduceOverall(a).overall) -
        overallRank(deriveReproduceOverall(b).overall);
      if (rankDiff !== 0) return rankDiff;
      return b.created_at.localeCompare(a.created_at);
    });
  }, [records, query, overall]);

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <Input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Filter by reproduce id or repo"
          aria-label="Filter reproductions by reproduce id or repo"
          className="h-9 sm:max-w-xs"
        />
        <DropdownMenu>
          <DropdownMenuTrigger
            render={<Button type="button" variant="outline" size="sm" className="h-9 gap-2" />}
          >
            <ListFilter className="size-4" aria-hidden="true" />
            <span>
              Overall
              {overall !== "all" ? (
                <span className="text-muted-foreground">: {overallLabel}</span>
              ) : null}
            </span>
            <ChevronDown className="size-4 opacity-60" aria-hidden="true" />
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-48">
            <DropdownMenuRadioGroup
              value={overall}
              onValueChange={(v) => setOverall(v as ReproduceOverall | "all")}
            >
              <DropdownMenuLabel>Filter by overall status</DropdownMenuLabel>
              <DropdownMenuSeparator />
              {OVERALL_FILTERS.map((f) => (
                <DropdownMenuRadioItem key={f.key} value={f.key}>
                  {f.label}
                </DropdownMenuRadioItem>
              ))}
            </DropdownMenuRadioGroup>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      <div className="overflow-hidden rounded-xl bg-card ring-1 ring-foreground/10">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead scope="col">Reproduce id</TableHead>
              <TableHead scope="col">Overall</TableHead>
              <TableHead scope="col">Repo</TableHead>
              <TableHead scope="col">Created</TableHead>
              <TableHead scope="col">Claims</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.length === 0 ? (
              <TableRow>
                <TableCell colSpan={5} className="text-center text-muted-foreground">
                  No reproductions match the current filters.
                </TableCell>
              </TableRow>
            ) : (
              rows.map((r) => {
                const derived = deriveReproduceOverall(r);
                const repo = r.repo || r.source_url || "—";
                return (
                  <TableRow key={r.reproduce_id}>
                    <TableCell>
                      <Link
                        href={`/reproduce/${r.reproduce_id}`}
                        className="rounded-sm font-mono text-sm font-medium text-foreground underline-offset-4 hover:text-brand hover:underline focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none"
                      >
                        {r.reproduce_id}
                      </Link>
                    </TableCell>
                    <TableCell>
                      <ReproduceStatusBadge
                        status={derived.overall}
                        exitCode={
                          derived.overall === "did_not_complete"
                            ? r.exit_code
                            : undefined
                        }
                      />
                    </TableCell>
                    <TableCell>
                      <span
                        title={repo}
                        className="block max-w-[18rem] truncate text-sm text-muted-foreground"
                      >
                        {repo}
                      </span>
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground whitespace-nowrap">
                      {new Date(r.created_at).toLocaleDateString()}
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground">
                      {claimCountsLine(derived.counts)}
                    </TableCell>
                  </TableRow>
                );
              })
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}