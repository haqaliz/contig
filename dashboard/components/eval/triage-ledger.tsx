// Jev triage ledger counts (C9). The engine appends one row per triaged
// decision to <runsDir>/triage-ledger.jsonl; this reads the rows the page
// already loaded and counts them (the counts-only half of `contig triage-stats`).
// No card when the ledger is absent: nothing has been triaged, so there is
// nothing to show. It never calls Jev and never claims calibration.
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { triageLedgerSummary } from "@/lib/derive";
import type { TriageLedgerRow } from "@/lib/types";

function countRows(counts: Record<string, number>) {
  return Object.entries(counts).sort(([a], [b]) => a.localeCompare(b));
}

export function TriageLedger({
  rows,
  skippedLines,
}: {
  rows: TriageLedgerRow[];
  skippedLines: number;
}) {
  if (rows.length === 0) return null;
  const summary = triageLedgerSummary(rows, skippedLines);

  return (
    <section className="flex flex-col gap-3" aria-labelledby="triage-ledger-heading">
      <h2 id="triage-ledger-heading" className="font-heading text-lg font-medium">
        Jev triage ledger
      </h2>
      <Card>
        <CardHeader className="border-b pb-4">
          <CardTitle className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
            {summary.total} triaged decision{summary.total === 1 ? "" : "s"}
            {summary.skipped > 0 ? ` · ${summary.skipped} skipped` : ""}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4 pt-5">
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <h3 className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
                By surface
              </h3>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead scope="col">Surface</TableHead>
                    <TableHead scope="col" className="text-right">
                      Rows
                    </TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {countRows(summary.bySurface).map(([surface, count]) => (
                    <TableRow key={surface}>
                      <TableHead scope="row" className="font-mono font-medium">
                        {surface}
                      </TableHead>
                      <TableCell className="text-right tabular-nums">{count}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
            <div>
              <h3 className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
                By mode
              </h3>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead scope="col">Mode</TableHead>
                    <TableHead scope="col" className="text-right">
                      Rows
                    </TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {countRows(summary.byMode).map(([mode, count]) => (
                    <TableRow key={mode}>
                      <TableHead scope="row" className="font-mono font-medium">
                        {mode}
                      </TableHead>
                      <TableCell className="text-right tabular-nums">{count}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </div>
          {summary.skippedLines > 0 ? (
            <p className="text-xs text-muted-foreground">
              {summary.skippedLines} unreadable ledger line
              {summary.skippedLines === 1 ? "" : "s"} skipped.
            </p>
          ) : null}
        </CardContent>
      </Card>
    </section>
  );
}
