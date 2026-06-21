// The detector eval view. This is a trust signal, not just an internal metric:
// it shows how Contig's failure detector scores against the labeled corpus, and
// frames that score as "how Contig is learning" from real runs. Server Component
// (no interactivity); it receives an already-fetched report as a prop.
import { CheckCircle2, AlertTriangle, TrendingUp } from "lucide-react";

import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Separator } from "@/components/ui/separator";
import { cn } from "@/lib/utils";
import type { ClassScore, DetectorEvalReport } from "@/lib/types";

/** Render a 0..1 ratio as a whole-number percentage (e.g. 0.5 -> "50%"). */
function pct(value: number): string {
  return `${Math.round(value * 100)}%`;
}

/** Render a 0..1 ratio as a fixed 2-decimal number (e.g. 0.5 -> "0.50"). */
function ratio(value: number): string {
  return value.toFixed(2);
}

export function EvalView({ report }: { report: DetectorEvalReport }) {
  // Sort classes by name so the table order is stable and scannable.
  const classes: Array<[string, ClassScore]> = Object.entries(report.per_class).sort(
    ([a], [b]) => a.localeCompare(b),
  );
  const hasMisses = report.mismatches.length > 0;

  return (
    <div className="flex flex-col gap-8">
      <header className="flex flex-col gap-1">
        <h1 className="font-heading text-2xl font-semibold tracking-tight">
          Detector eval
        </h1>
        <p className="text-sm text-muted-foreground">
          How Contig is learning: the failure detector scored against the labeled
          corpus of known failures.
        </p>
      </header>

      {/* Headline: accuracy as the trust signal. */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <TrendingUp className="size-4 text-muted-foreground" aria-hidden="true" />
            Accuracy
          </CardTitle>
          <CardDescription>
            The detector correctly classified {report.correct} of {report.total} known
            failures.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex items-baseline gap-3">
            <span className="font-heading text-5xl font-semibold tracking-tight tabular-nums">
              {pct(report.accuracy)}
            </span>
            <span className="text-sm text-muted-foreground tabular-nums">
              {report.correct} / {report.total} cases correct
            </span>
          </div>
        </CardContent>
      </Card>

      {/* Per-class breakdown. */}
      <section className="flex flex-col gap-3" aria-labelledby="per-class-heading">
        <h2 id="per-class-heading" className="font-heading text-lg font-medium">
          Per-class scores
        </h2>
        <Card>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead scope="col">Class</TableHead>
                  <TableHead scope="col" className="text-right">
                    Precision
                  </TableHead>
                  <TableHead scope="col" className="text-right">
                    Recall
                  </TableHead>
                  <TableHead scope="col" className="text-right">
                    Support
                  </TableHead>
                  <TableHead scope="col" className="text-right">
                    Predicted
                  </TableHead>
                  <TableHead scope="col" className="text-right">
                    Correct
                  </TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {classes.map(([name, score]) => {
                  const incompleteRecall = score.recall < 1;
                  return (
                    <TableRow
                      key={name}
                      className={cn(incompleteRecall && "bg-amber-50/60 dark:bg-amber-950/30")}
                    >
                      <TableHead
                        scope="row"
                        className="font-medium whitespace-normal"
                      >
                        <span className="flex items-center gap-1.5">
                          {incompleteRecall && (
                            <AlertTriangle
                              className="size-3.5 text-amber-600 dark:text-amber-400"
                              aria-label="Recall below 100 percent"
                            />
                          )}
                          <span className="font-mono">{name}</span>
                        </span>
                      </TableHead>
                      <TableCell className="text-right tabular-nums">
                        {pct(score.precision)}{" "}
                        <span className="text-muted-foreground">
                          ({ratio(score.precision)})
                        </span>
                      </TableCell>
                      <TableCell className="text-right tabular-nums">
                        {pct(score.recall)}{" "}
                        <span className="text-muted-foreground">
                          ({ratio(score.recall)})
                        </span>
                      </TableCell>
                      <TableCell className="text-right tabular-nums">
                        {score.support}
                      </TableCell>
                      <TableCell className="text-right tabular-nums">
                        {score.predicted}
                      </TableCell>
                      <TableCell className="text-right tabular-nums">
                        {score.correct}
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      </section>

      {/* Current misses: each mismatch the detector still gets wrong. */}
      <section className="flex flex-col gap-3" aria-labelledby="misses-heading">
        <h2 id="misses-heading" className="font-heading text-lg font-medium">
          Current misses
        </h2>
        <Card>
          <CardContent>
            {hasMisses ? (
              <ul className="flex flex-col divide-y">
                {report.mismatches.map((m) => (
                  <li
                    key={m.case_id}
                    className="flex flex-col gap-1 py-3 first:pt-0 last:pb-0 sm:flex-row sm:items-center sm:justify-between sm:gap-4"
                  >
                    <span className="flex items-center gap-2 font-mono text-sm">
                      <AlertTriangle
                        className="size-3.5 shrink-0 text-amber-600 dark:text-amber-400"
                        aria-hidden="true"
                      />
                      {m.case_id}
                    </span>
                    <span className="text-sm text-muted-foreground">
                      expected{" "}
                      <span className="font-mono text-foreground">{m.expected}</span>,
                      predicted{" "}
                      <span className="font-mono text-foreground">{m.predicted}</span>
                    </span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="flex items-center gap-2 py-1 text-sm text-emerald-800 dark:text-emerald-300">
                <CheckCircle2 className="size-4 shrink-0" aria-hidden="true" />
                No misses: every labeled case was classified correctly.
              </p>
            )}
          </CardContent>
        </Card>
      </section>

      <Separator />

      <footer className="text-sm text-muted-foreground">
        This corpus grows automatically from real runs, so the score reflects live
        coverage. A drop in accuracy flags a regression in the detector or a new gap
        the corpus has started to surface.
      </footer>
    </div>
  );
}
