"use client";

// Interactive run list: text filter (run id or pipeline), verdict filter buttons,
// and a click-to-sort Tasks column. Default sort is by verdict severity (fail
// first) so the runs that need attention float to the top. All trust logic stays
// in the engine: we only read the serialized verdict and derive display counts.
import { useMemo, useState } from "react";
import Link from "next/link";
import { ChevronDown, ListFilter, Wrench } from "lucide-react";

import { Badge } from "@/components/ui/badge";
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
import { StatusBadge } from "@/components/status-badge";
import { taskCounts, wasRepaired, VERDICT_ORDER } from "@/lib/derive";
import type { RunRecord, Verdict } from "@/lib/types";

// The verdict filter buttons. "all" keeps everything; the rest match one verdict.
const VERDICT_FILTERS: { key: Verdict | "all"; label: string }[] = [
  { key: "all", label: "All" },
  { key: "fail", label: "Fail" },
  { key: "warn", label: "Warn" },
  { key: "unverified", label: "Unverified" },
  { key: "pass", label: "Pass" },
];

type TaskSort = "none" | "asc" | "desc";

export function RunsTable({ runs }: { runs: RunRecord[] }) {
  const [query, setQuery] = useState("");
  const [verdict, setVerdict] = useState<Verdict | "all">("all");
  // "none" means the default severity sort. Clicking Tasks cycles desc -> asc -> none.
  const [taskSort, setTaskSort] = useState<TaskSort>("none");

  const verdictLabel =
    VERDICT_FILTERS.find((f) => f.key === verdict)?.label ?? "All";

  const rows = useMemo(() => {
    const q = query.trim().toLowerCase();

    const filtered = runs.filter((r) => {
      if (verdict !== "all" && r.verdict !== verdict) return false;
      if (q.length === 0) return true;
      return (
        r.run_id.toLowerCase().includes(q) ||
        r.pipeline.toLowerCase().includes(q)
      );
    });

    const sorted = [...filtered];
    if (taskSort === "none") {
      // Default: worst verdict first (fail, warn, unverified, pass).
      sorted.sort((a, b) => VERDICT_ORDER[a.verdict] - VERDICT_ORDER[b.verdict]);
    } else {
      sorted.sort((a, b) => {
        const fa = taskCounts(a).failed;
        const fb = taskCounts(b).failed;
        return taskSort === "asc" ? fa - fb : fb - fa;
      });
    }
    return sorted;
  }, [runs, query, verdict, taskSort]);

  function cycleTaskSort() {
    setTaskSort((prev) =>
      prev === "none" ? "desc" : prev === "desc" ? "asc" : "none",
    );
  }

  const taskSortLabel =
    taskSort === "asc"
      ? "sorted by failed tasks ascending"
      : taskSort === "desc"
        ? "sorted by failed tasks descending"
        : "not sorted by tasks";
  const taskAriaSort =
    taskSort === "asc" ? "ascending" : taskSort === "desc" ? "descending" : "none";

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <Input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Filter by run id or pipeline"
          aria-label="Filter runs by run id or pipeline"
          className="sm:max-w-xs"
        />
        <DropdownMenu>
          <DropdownMenuTrigger
            render={<Button type="button" variant="outline" size="sm" className="gap-2" />}
          >
            <ListFilter className="size-4" aria-hidden="true" />
            <span>
              Verdict
              {verdict !== "all" ? (
                <span className="text-muted-foreground">: {verdictLabel}</span>
              ) : null}
            </span>
            <ChevronDown className="size-4 opacity-60" aria-hidden="true" />
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-44">
            <DropdownMenuLabel>Filter by verdict</DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuRadioGroup
              value={verdict}
              onValueChange={(v) => setVerdict(v as Verdict | "all")}
            >
              {VERDICT_FILTERS.map((f) => (
                <DropdownMenuRadioItem key={f.key} value={f.key}>
                  {f.label}
                </DropdownMenuRadioItem>
              ))}
            </DropdownMenuRadioGroup>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      <Table>
        <TableHeader>
          <TableRow>
            <TableHead scope="col">Run id</TableHead>
            <TableHead scope="col">Verdict</TableHead>
            <TableHead scope="col">Pipeline</TableHead>
            <TableHead scope="col" aria-sort={taskAriaSort}>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="-ml-2"
                onClick={cycleTaskSort}
                aria-label={`Tasks, ${taskSortLabel}. Activate to change sorting.`}
              >
                Tasks
                <span aria-hidden="true">
                  {taskSort === "asc" ? "↑" : taskSort === "desc" ? "↓" : ""}
                </span>
              </Button>
            </TableHead>
            <TableHead scope="col">Repaired</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.length === 0 ? (
            <TableRow>
              <TableCell colSpan={5} className="text-center text-muted-foreground">
                No runs match the current filters.
              </TableCell>
            </TableRow>
          ) : (
            rows.map((r) => {
              const counts = taskCounts(r);
              return (
                <TableRow key={r.run_id}>
                  <TableCell>
                    <Link
                      href={`/runs/${r.run_id}`}
                      className="font-mono text-sm underline-offset-4 hover:underline"
                    >
                      {r.run_id}
                    </Link>
                  </TableCell>
                  <TableCell>
                    <StatusBadge status={r.verdict} />
                  </TableCell>
                  <TableCell className="text-sm">
                    {r.pipeline} @ {r.pipeline_revision}
                  </TableCell>
                  <TableCell className="font-mono text-sm tabular-nums">
                    <span className={counts.failed > 0 ? "text-red-600 dark:text-red-400" : undefined}>
                      {counts.failed}
                    </span>
                    <span className="text-muted-foreground"> / {counts.total}</span>
                  </TableCell>
                  <TableCell>
                    {wasRepaired(r) ? (
                      <Badge variant="secondary" className="gap-1">
                        <Wrench className="size-3.5" aria-hidden="true" />
                        Repaired
                      </Badge>
                    ) : (
                      <span className="text-muted-foreground">-</span>
                    )}
                  </TableCell>
                </TableRow>
              );
            })
          )}
        </TableBody>
      </Table>
    </div>
  );
}
