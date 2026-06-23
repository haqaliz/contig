// Side-by-side detector comparison (PRD contract A). The LLM-detector proof: the
// user records an llm-tagged eval snapshot with their own key (`contig
// eval-detector --detector llm --snapshot`); this view puts the latest snapshot
// per detector (rules, rules-strict, llm) next to each other so a reader can see,
// directly, whether the optional LLM detector beats the rules baseline, overall
// and per failure class. It reads the same committed eval-history the trend reads,
// grouped by the snapshot's `detector` field. Server Component: it receives the
// already-loaded history and renders. The trend below it is unchanged.
import { Sparkles } from "lucide-react";

import {
  Card,
  CardContent,
  CardDescription,
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
import { cn } from "@/lib/utils";
import type { EvalSnapshot } from "@/lib/types";

// The detectors we compare, in a stable order so the columns never reshuffle. A
// snapshot with no `detector` field predates the tag and is treated as "rules".
const DETECTOR_ORDER = ["rules", "rules-strict", "llm"] as const;
type DetectorKey = (typeof DETECTOR_ORDER)[number];

// A short, human label for each detector column header.
const DETECTOR_LABEL: Record<DetectorKey, string> = {
  rules: "Rules",
  "rules-strict": "Rules (strict)",
  llm: "LLM",
};

function pct(value: number): string {
  return `${Math.round(value * 100)}%`;
}

/** The detector a snapshot belongs to, defaulting an untagged one to "rules". */
function detectorOf(snap: EvalSnapshot): string {
  return snap.detector ?? "rules";
}

/**
 * The latest snapshot per detector, in file (chronological) order so the last one
 * for each detector wins. Only the detectors we know how to render are kept, and
 * only those that actually have a snapshot appear as a column.
 */
function latestPerDetector(
  history: EvalSnapshot[],
): { detector: DetectorKey; snapshot: EvalSnapshot }[] {
  const latest = new Map<string, EvalSnapshot>();
  for (const snap of history) {
    latest.set(detectorOf(snap), snap);
  }
  return DETECTOR_ORDER.filter((d) => latest.has(d)).map((d) => ({
    detector: d,
    snapshot: latest.get(d)!,
  }));
}

export function DetectorCompare({ history }: { history: EvalSnapshot[] }) {
  const columns = latestPerDetector(history);

  // With fewer than two detectors there is nothing to compare. We still render a
  // short, honest prompt so the user knows how to produce the comparison (run the
  // llm detector with their own key).
  if (columns.length < 2) {
    return (
      <section
        className="flex flex-col gap-3"
        aria-labelledby="detector-compare-heading"
      >
        <h2
          id="detector-compare-heading"
          className="font-heading text-lg font-medium"
        >
          Detector comparison
        </h2>
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Sparkles className="size-4 text-muted-foreground" aria-hidden="true" />
              Only one detector recorded so far
            </CardTitle>
            <CardDescription>
              Record a snapshot for a second detector to compare them here. Run{" "}
              <code className="font-mono">
                contig eval-detector --detector llm --snapshot
              </code>{" "}
              with a provider and key configured to add an LLM-tagged point, then
              this view shows rules vs LLM side by side.
            </CardDescription>
          </CardHeader>
        </Card>
      </section>
    );
  }

  // Every class seen across the compared snapshots, sorted, so a class only one
  // detector reports still gets a row (the other column reads n/a there).
  const classKeys = new Set<string>();
  for (const col of columns) {
    for (const k of Object.keys(col.snapshot.per_class)) classKeys.add(k);
  }
  const classes = [...classKeys].sort((a, b) => a.localeCompare(b));

  // The best overall accuracy across the columns, to highlight the leader honestly
  // (a tie highlights every leader). Used only for emphasis, never as a verdict.
  const bestAccuracy = Math.max(...columns.map((c) => c.snapshot.accuracy));

  return (
    <section
      className="flex flex-col gap-3"
      aria-labelledby="detector-compare-heading"
    >
      <h2
        id="detector-compare-heading"
        className="font-heading text-lg font-medium"
      >
        Detector comparison
      </h2>
      <Card>
        <CardHeader>
          <CardTitle className="text-base">
            Latest snapshot per detector
          </CardTitle>
          <CardDescription>
            The most recent eval for each detector, side by side: overall accuracy
            and per-class recall. The LLM detector is optional and only appears once
            you have recorded an LLM-tagged snapshot with your own key.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead scope="col">Class</TableHead>
                {columns.map((col) => (
                  <TableHead
                    key={col.detector}
                    scope="col"
                    className="text-right"
                  >
                    {DETECTOR_LABEL[col.detector]}
                  </TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {/* Headline accuracy row, the direct rules-vs-llm comparison. */}
              <TableRow className="border-b-2">
                <TableHead scope="row" className="font-medium">
                  Overall accuracy
                </TableHead>
                {columns.map((col) => {
                  const isLeader =
                    col.snapshot.accuracy >= bestAccuracy && columns.length > 1;
                  return (
                    <TableCell
                      key={col.detector}
                      className={cn(
                        "text-right font-semibold tabular-nums",
                        isLeader &&
                          "text-emerald-700 dark:text-emerald-400",
                      )}
                    >
                      {pct(col.snapshot.accuracy)}
                    </TableCell>
                  );
                })}
              </TableRow>
              {/* Per-class recall, the granular comparison. */}
              {classes.map((name) => (
                <TableRow key={name}>
                  <TableHead
                    scope="row"
                    className="font-mono font-normal whitespace-normal"
                  >
                    {name}
                  </TableHead>
                  {columns.map((col) => {
                    const score = col.snapshot.per_class[name];
                    return (
                      <TableCell
                        key={col.detector}
                        className="text-right tabular-nums"
                      >
                        {score ? (
                          pct(score.recall)
                        ) : (
                          <span className="text-muted-foreground">n/a</span>
                        )}
                      </TableCell>
                    );
                  })}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </section>
  );
}
