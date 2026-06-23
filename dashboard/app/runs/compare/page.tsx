// Run compare / diff view (Server Component). It answers the reproducibility
// question directly: pick two runs (a baseline and a re-run) and see, field by
// field, whether the re-run reproduced and exactly what changed. The data fetch
// (getRun, listRuns) stays on the server; the only client island is the picker.
//
// NEXT 16: searchParams is a Promise and must be awaited.
import Link from "next/link";
import { ArrowLeft, CheckCircle2, AlertTriangle } from "lucide-react";

import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
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
import { currentViewer } from "@/lib/auth0";
import { getRun, listRuns } from "@/lib/runs";
import { diffRuns } from "@/lib/diff";
import type {
  DiffState,
  MapDiff,
  QcDiff,
  RunDiff,
} from "@/lib/diff";
import { cn } from "@/lib/utils";
import { RunPicker } from "./run-picker";

// Read fresh on every request so the comparison reflects the runs on disk.
export const dynamic = "force-dynamic";

// Row tint by diff state. "same" stays neutral; anything that differs is tinted
// amber so a re-run that did not reproduce is obvious at a glance. Color is never
// the only signal: each changed row also carries a "Changed" / "Added" /
// "Removed" status cell.
const STATE_ROW: Record<DiffState, string> = {
  same: "",
  changed: "bg-amber-50/70 dark:bg-amber-950/30",
  added: "bg-amber-50/70 dark:bg-amber-950/30",
  removed: "bg-amber-50/70 dark:bg-amber-950/30",
};

const STATE_LABEL: Record<DiffState, string> = {
  same: "Same",
  changed: "Changed",
  added: "Only in B",
  removed: "Only in A",
};

function StateCell({ state }: { state: DiffState }) {
  if (state === "same") {
    return <span className="text-xs text-muted-foreground">Same</span>;
  }
  return (
    <span className="text-xs font-medium text-amber-700 dark:text-amber-400">
      {STATE_LABEL[state]}
    </span>
  );
}

// A monospace value cell; renders an em-free placeholder when the key is absent
// on that side of the comparison.
function ValueCell({ value }: { value: string | null }) {
  if (value === null) {
    return <span className="text-xs text-muted-foreground italic">absent</span>;
  }
  if (value === "") {
    return <span className="text-xs text-muted-foreground italic">(empty)</span>;
  }
  return (
    <span title={value} className="block max-w-[32ch] truncate font-mono text-xs">
      {value}
    </span>
  );
}

function MapDiffCard({
  title,
  description,
  keyLabel,
  diff,
  idA,
  idB,
}: {
  title: string;
  description?: string;
  keyLabel: string;
  diff: MapDiff;
  idA: string;
  idB: string;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          {title}
          {diff.identical ? (
            <span className="text-xs font-normal text-muted-foreground">
              (matches)
            </span>
          ) : (
            <span className="text-xs font-normal text-amber-700 dark:text-amber-400">
              ({diff.changedCount} differ)
            </span>
          )}
        </CardTitle>
        {description ? <CardDescription>{description}</CardDescription> : null}
      </CardHeader>
      <CardContent>
        {diff.entries.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            Neither run recorded any {keyLabel.toLowerCase()}.
          </p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead scope="col">{keyLabel}</TableHead>
                <TableHead scope="col" className="font-mono">{idA}</TableHead>
                <TableHead scope="col" className="font-mono">{idB}</TableHead>
                <TableHead scope="col">State</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {diff.entries.map((e) => (
                <TableRow key={e.key} className={STATE_ROW[e.state]}>
                  <TableHead
                    scope="row"
                    className="font-mono text-xs font-normal whitespace-normal"
                  >
                    {e.key}
                  </TableHead>
                  <TableCell className="whitespace-normal">
                    <ValueCell value={e.a} />
                  </TableCell>
                  <TableCell className="whitespace-normal">
                    <ValueCell value={e.b} />
                  </TableCell>
                  <TableCell>
                    <StateCell state={e.state} />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}

function QcDiffCard({ diff, idA, idB }: { diff: QcDiff; idA: string; idB: string }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          QC checks
          {diff.identical ? (
            <span className="text-xs font-normal text-muted-foreground">
              (matches)
            </span>
          ) : (
            <span className="text-xs font-normal text-amber-700 dark:text-amber-400">
              ({diff.changedCount} differ)
            </span>
          )}
        </CardTitle>
        <CardDescription>
          Each check compared by status and value. The QC verdict is computed by
          the engine, not re-derived here.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {diff.entries.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            Neither run recorded any QC checks.
          </p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead scope="col">Check</TableHead>
                <TableHead scope="col" className="font-mono">{idA}</TableHead>
                <TableHead scope="col" className="font-mono">{idB}</TableHead>
                <TableHead scope="col">State</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {diff.entries.map((e) => (
                <TableRow key={e.check} className={STATE_ROW[e.state]}>
                  <TableHead
                    scope="row"
                    className="font-mono text-xs font-normal whitespace-normal"
                  >
                    {e.check}
                  </TableHead>
                  <TableCell>
                    {e.a ? (
                      <span className="flex items-center gap-2">
                        <StatusBadge status={e.a.status} />
                        <span className="font-mono text-xs tabular-nums text-muted-foreground">
                          {e.a.value ?? "n/a"}
                        </span>
                      </span>
                    ) : (
                      <span className="text-xs text-muted-foreground italic">absent</span>
                    )}
                  </TableCell>
                  <TableCell>
                    {e.b ? (
                      <span className="flex items-center gap-2">
                        <StatusBadge status={e.b.status} />
                        <span className="font-mono text-xs tabular-nums text-muted-foreground">
                          {e.b.value ?? "n/a"}
                        </span>
                      </span>
                    ) : (
                      <span className="text-xs text-muted-foreground italic">absent</span>
                    )}
                  </TableCell>
                  <TableCell>
                    <StateCell state={e.state} />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}

function SummaryCard({ diff }: { diff: RunDiff }) {
  const Icon = diff.reproduced ? CheckCircle2 : AlertTriangle;
  return (
    <Card
      className={cn(
        "ring-1",
        diff.reproduced
          ? "ring-emerald-300/60 dark:ring-emerald-800/60"
          : "ring-amber-300/60 dark:ring-amber-800/60",
      )}
    >
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Icon
            className={cn(
              "size-5",
              diff.reproduced
                ? "text-emerald-600 dark:text-emerald-400"
                : "text-amber-600 dark:text-amber-400",
            )}
            aria-hidden="true"
          />
          {diff.reproduced ? "Reproduced" : "Did not reproduce"}
        </CardTitle>
        <CardDescription>
          {diff.reproduced
            ? "Verdict, pipeline, parameters, checksums, task counts, and QC all match across the two runs."
            : "At least one field differs between the two runs. Differing rows below are highlighted."}
        </CardDescription>
      </CardHeader>
      <CardContent>
        <dl className="grid grid-cols-2 gap-4 sm:grid-cols-3">
          <div>
            <dt className="text-xs text-muted-foreground">Verdict ({diff.idA})</dt>
            <dd className="mt-1">
              <StatusBadge status={diff.verdict.a} />
            </dd>
          </div>
          <div>
            <dt className="text-xs text-muted-foreground">Verdict ({diff.idB})</dt>
            <dd className="mt-1">
              <StatusBadge status={diff.verdict.b} />
            </dd>
          </div>
          <div>
            <dt className="text-xs text-muted-foreground">Tasks (failed / total)</dt>
            <dd
              className={cn(
                "mt-1 font-mono text-sm tabular-nums",
                diff.taskCounts.state === "changed"
                  ? "text-amber-700 dark:text-amber-400"
                  : "text-foreground",
              )}
            >
              {diff.taskCounts.a.failed}/{diff.taskCounts.a.total} vs{" "}
              {diff.taskCounts.b.failed}/{diff.taskCounts.b.total}
            </dd>
          </div>
        </dl>
      </CardContent>
    </Card>
  );
}

function ScalarRow({
  label,
  a,
  b,
  state,
}: {
  label: string;
  a: string;
  b: string;
  state: "same" | "changed";
}) {
  return (
    <TableRow className={state === "changed" ? STATE_ROW.changed : ""}>
      <TableHead scope="row" className="text-xs font-normal whitespace-normal">
        {label}
      </TableHead>
      <TableCell className="font-mono text-xs break-words">{a}</TableCell>
      <TableCell className="font-mono text-xs break-words">{b}</TableCell>
      <TableCell>
        <StateCell state={state} />
      </TableCell>
    </TableRow>
  );
}

export default async function CompareRunsPage({
  searchParams,
}: {
  searchParams: Promise<{ a?: string; b?: string }>;
}) {
  const { a, b } = await searchParams;

  // Per-user isolation (PRD contract E): both the picked runs and the picker list
  // are scoped to this viewer, so a user can only compare runs they may see.
  const viewer = await currentViewer();
  const recordA = a ? await getRun(a, viewer) : null;
  const recordB = b ? await getRun(b, viewer) : null;

  // The picker stays on screen in both states (empty and showing a comparison)
  // so the user can swap either run without first navigating away. It is always
  // pre-filled with the current selection.
  const runs = await listRuns(viewer);
  const runIds = runs.map((r) => r.run_id).sort();

  const pickerCard = (
    <Card>
      <CardHeader>
        <CardTitle>Choose two runs</CardTitle>
        <CardDescription>
          Select a baseline and a comparison run, then compare. A run picked on
          one side is removed from the other.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <RunPicker runIds={runIds} initialA={a} initialB={b} />
      </CardContent>
    </Card>
  );

  const header = (
    <>
      <Link
        href="/runs"
        className="inline-flex items-center gap-1 rounded-sm text-sm text-muted-foreground transition-colors hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none"
      >
        <ArrowLeft className="size-4" aria-hidden="true" />
        All runs
      </Link>
      <PageHeader
        title="Compare runs"
        description="Pick two runs (a baseline and a re-run) to see whether the re-run reproduced, and if not, exactly what changed: verdict, pipeline, parameters, checksums, container digests, task counts, and QC."
      />
    </>
  );

  // Missing or not-found ids fall back to the pickers. We surface a hint when an
  // id was supplied but no bundle was found on disk.
  if (!recordA || !recordB) {
    const notFound: string[] = [];
    if (a && !recordA) notFound.push(a);
    if (b && !recordB) notFound.push(b);

    return (
      <div className="mx-auto w-full max-w-5xl space-y-6">
        {header}
        {pickerCard}
        {notFound.length > 0 ? (
          <p className="rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-800 dark:bg-amber-950/40 dark:text-amber-300">
            No run bundle found for: {notFound.map((id) => (
              <code key={id} className="mx-1 font-mono">{id}</code>
            ))}
          </p>
        ) : null}
      </div>
    );
  }

  const diff = diffRuns(recordA, recordB);

  return (
    <div className="mx-auto w-full max-w-5xl space-y-6">
      {header}

      {pickerCard}

      <p className="text-sm text-muted-foreground">
        Comparing{" "}
        <Link
          href={`/runs/${diff.idA}`}
          className="font-mono font-medium text-foreground underline-offset-4 hover:underline"
        >
          {diff.idA}
        </Link>{" "}
        (A) against{" "}
        <Link
          href={`/runs/${diff.idB}`}
          className="font-mono font-medium text-foreground underline-offset-4 hover:underline"
        >
          {diff.idB}
        </Link>{" "}
        (B).
      </p>

      <SummaryCard diff={diff} />

      <Card>
        <CardHeader>
          <CardTitle>Identity</CardTitle>
          <CardDescription>
            Verdict, pipeline, and revision compared side by side.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead scope="col">Field</TableHead>
                <TableHead scope="col" className="font-mono">{diff.idA}</TableHead>
                <TableHead scope="col" className="font-mono">{diff.idB}</TableHead>
                <TableHead scope="col">State</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              <TableRow
                className={diff.verdict.state === "changed" ? STATE_ROW.changed : ""}
              >
                <TableHead scope="row" className="text-xs font-normal whitespace-normal">
                  Verdict
                </TableHead>
                <TableCell>
                  <StatusBadge status={diff.verdict.a} />
                </TableCell>
                <TableCell>
                  <StatusBadge status={diff.verdict.b} />
                </TableCell>
                <TableCell>
                  <StateCell state={diff.verdict.state} />
                </TableCell>
              </TableRow>
              <ScalarRow
                label={diff.pipeline.label}
                a={diff.pipeline.a}
                b={diff.pipeline.b}
                state={diff.pipeline.state}
              />
              <ScalarRow
                label={diff.revision.label}
                a={diff.revision.a}
                b={diff.revision.b}
                state={diff.revision.state}
              />
              <ScalarRow
                label="Tasks (failed / total)"
                a={`${diff.taskCounts.a.failed} / ${diff.taskCounts.a.total}`}
                b={`${diff.taskCounts.b.failed} / ${diff.taskCounts.b.total}`}
                state={diff.taskCounts.state}
              />
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <MapDiffCard
        title="Parameters"
        keyLabel="Parameter"
        diff={diff.parameters}
        idA={diff.idA}
        idB={diff.idB}
      />

      <QcDiffCard diff={diff.qc} idA={diff.idA} idB={diff.idB} />

      <MapDiffCard
        title="Input checksums"
        description="Same inputs hash to the same value. A changed input checksum means the run was fed different data."
        keyLabel="Input"
        diff={diff.inputChecksums}
        idA={diff.idA}
        idB={diff.idB}
      />

      <MapDiffCard
        title="Output checksums"
        description="Matching output checksums are the strongest signal of a bit-for-bit reproduction."
        keyLabel="Output"
        diff={diff.outputChecksums}
        idA={diff.idA}
        idB={diff.idB}
      />

      <MapDiffCard
        title="Container digests"
        keyLabel="Container"
        diff={diff.containerDigests}
        idA={diff.idA}
        idB={diff.idB}
      />
    </div>
  );
}
