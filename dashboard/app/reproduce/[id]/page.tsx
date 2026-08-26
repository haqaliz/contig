// Per-run audit surface for a third-party `contig reproduce` bundle (C8): the
// derived overall status, provenance pins, per-claim table, repair history,
// signature presence, and single-file bundle downloads. Server Component: it
// reads the bundle straight off disk via lib/reproduce and renders it; the
// trust logic (per-claim statuses, the signature sidecar) stays in the engine,
// the dashboard only derives the display overall (worst-of) client-side-safe
// in lib/reproduce-derive. Honesty rules: unverified never renders as
// reproduced, the freshness message renders verbatim, and the signature card
// shows presence only (no verification claim).
import Link from "next/link";
import { notFound } from "next/navigation";
import {
  ArrowLeft,
  CheckCircle2,
  FileJson,
  FileKey2,
  FileText,
  ShieldCheck,
} from "lucide-react";

import { PageHeader } from "@/components/page-header";
import { ReproduceStatusBadge } from "@/components/reproduce-status-badge";
import { Badge } from "@/components/ui/badge";
import { buttonVariants } from "@/components/ui/button";
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
import { deriveReproduceOverall } from "@/lib/reproduce-derive";
import {
  readReproduceManifest,
  readReproduceRecord,
  readReproduceSignature,
} from "@/lib/reproduce";
import type {
  ReproduceClaim,
  ReproduceRepairStep,
} from "@/lib/types";

// The bundle is written by whatever contig version the user ran, possibly
// newer than this dashboard, so always read fresh.
export const dynamic = "force-dynamic";

// A hash/digest cell: monospace, middle-truncated (~12/12), full value on
// hover (title), the provenance-panel convention.
function Hash({ value }: { value: string }) {
  const shown =
    value.length > 25 ? `${value.slice(0, 12)}…${value.slice(-12)}` : value;
  return (
    <span
      title={value}
      className="block max-w-[30ch] font-mono text-xs break-all"
    >
      {shown}
    </span>
  );
}

// A numeric claim value. null renders as "-" (never "0" or a fabricated
// number); integers drop their decimals, small deltas keep 4 significant
// fraction digits (the qc-panel formatting convention).
function ClaimValue({ value }: { value: number | null }) {
  if (value === null) {
    return <span className="text-muted-foreground">-</span>;
  }
  return (
    <span className="font-mono text-xs tabular-nums">
      {Number.isInteger(value)
        ? value.toLocaleString("en-US")
        : value.toLocaleString("en-US", { maximumFractionDigits: 4 })}
    </span>
  );
}

function ClaimsTable({ claims }: { claims: ReproduceClaim[] }) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead scope="col">Claim</TableHead>
          <TableHead scope="col">Status</TableHead>
          <TableHead scope="col" className="text-right">
            Claimed
          </TableHead>
          <TableHead scope="col" className="text-right">
            Observed
          </TableHead>
          <TableHead scope="col" className="text-right">
            Tolerance
          </TableHead>
          <TableHead scope="col" className="text-right">
            Delta
          </TableHead>
          <TableHead scope="col">Message</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {claims.length === 0 ? (
          <TableRow>
            <TableCell
              colSpan={7}
              className="text-center text-muted-foreground"
            >
              No claims recorded.
            </TableCell>
          </TableRow>
        ) : (
          claims.map((c) => (
            <TableRow key={c.id}>
              <TableCell className="font-mono text-xs whitespace-normal">
                {c.id}
              </TableCell>
              <TableCell>
                <ReproduceStatusBadge status={c.status} />
              </TableCell>
              <TableCell className="text-right">
                <ClaimValue value={c.claimed} />
              </TableCell>
              <TableCell className="text-right">
                <ClaimValue value={c.observed} />
              </TableCell>
              <TableCell className="text-right">
                <ClaimValue value={c.tolerance} />
              </TableCell>
              <TableCell className="text-right">
                <ClaimValue value={c.delta} />
              </TableCell>
              {/* The engine's wording renders verbatim: freshness and
                  unresolved-locator messages are the honest answer, never
                  editorialized. */}
              <TableCell className="max-w-[24rem] whitespace-normal text-muted-foreground">
                {c.message || "—"}
              </TableCell>
            </TableRow>
          ))
        )}
      </TableBody>
    </Table>
  );
}

// One env-repair line in the repair-timeline mould: outcome literal,
// patch_applied marker (rendered only when true), the install operation, the
// detail, and the diagnosis's root cause. The applied marker never appears for
// a step that was not enacted (patch_applied is False) -- that would
// over-claim.
function RepairStepCard({ step }: { step: ReproduceRepairStep }) {
  const installOp = step.patch?.operation?.install;
  return (
    <li className="relative pl-8">
      <span
        className="absolute top-1.5 left-2.5 size-3 -translate-x-1/2 rounded-full bg-foreground/70 ring-4 ring-background"
        aria-hidden="true"
      />
      <div className="space-y-2 rounded-lg ring-1 ring-foreground/10 p-4">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm font-medium">Attempt {step.attempt}</span>
          <code className="rounded bg-muted/60 px-1.5 py-0.5 font-mono text-xs">
            {step.outcome}
          </code>
          {step.patch_applied ? (
            <Badge
              variant="outline"
              className="gap-1 border-emerald-300 bg-emerald-50 font-medium text-emerald-800 dark:border-emerald-800 dark:bg-emerald-950 dark:text-emerald-300"
            >
              <CheckCircle2 className="size-3.5" aria-hidden="true" />
              Applied
            </Badge>
          ) : null}
        </div>
        {step.patch ? (
          <p className="text-xs">
            <span className="text-muted-foreground">
              {step.patch.kind} patch
              {typeof installOp === "string" ? ": install " : ""}
            </span>
            {typeof installOp === "string" ? (
              <code className="font-mono text-xs">{installOp}</code>
            ) : null}
            <span className="ml-2 text-muted-foreground">
              {step.patch.rationale}
            </span>
          </p>
        ) : null}
        {step.detail ? <p className="text-sm">{step.detail}</p> : null}
        <p className="text-sm text-muted-foreground">
          {step.diagnosis.root_cause}
        </p>
      </div>
    </li>
  );
}

export default async function ReproduceDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const record = await readReproduceRecord(id);
  if (!record) {
    notFound();
  }
  // The manifest is unsigned invocation metadata; may be absent (defensive:
  // the page renders provenance from the record alone).
  const manifest = await readReproduceManifest(id);
  const signature = await readReproduceSignature(id);
  const derived = deriveReproduceOverall(record);
  const repo = record.repo || record.source_url || "—";
  const didNotComplete = derived.overall === "did_not_complete";
  const downloadBase = `/api/reproduce/${encodeURIComponent(id)}/download`;

  return (
    <div className="mx-auto w-full max-w-5xl space-y-6">
      <Link
        href="/reproduce"
        className="inline-flex items-center gap-1 rounded-sm text-sm text-muted-foreground transition-colors hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none"
      >
        <ArrowLeft className="size-4" aria-hidden="true" />
        All reproductions
      </Link>

      <PageHeader
        title={record.reproduce_id}
        titleClassName="font-mono break-all"
        description={
          <span className="font-mono break-all">{record.run_command}</span>
        }
      />

      <section aria-label="Reproduction summary">
        <Card>
          <CardHeader className="gap-3 border-b pb-4">
            <CardTitle className="flex flex-wrap items-center gap-3 text-lg">
              <ReproduceStatusBadge
                status={derived.overall}
                exitCode={didNotComplete ? record.exit_code : undefined}
                size="lg"
              />
              <span className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
                Overall
              </span>
            </CardTitle>
            <CardDescription className="text-base leading-relaxed text-foreground">
              {didNotComplete
                ? `The run did not complete (exit ${record.exit_code}); its claims read as recorded.`
                : "The derived worst-of over the claim statuses."}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <dl className="grid grid-cols-2 gap-x-4 gap-y-3 sm:grid-cols-4">
              <div>
                <dt className="text-xs text-muted-foreground">Repository</dt>
                <dd className="font-mono text-xs break-all">{repo}</dd>
              </div>
              <div>
                <dt className="text-xs text-muted-foreground">Run command</dt>
                <dd className="font-mono text-xs break-all">{record.run_command}</dd>
              </div>
              <div>
                <dt className="text-xs text-muted-foreground">Created</dt>
                <dd className="text-xs">
                  {new Date(record.created_at).toLocaleDateString()}
                </dd>
              </div>
              <div>
                <dt className="text-xs text-muted-foreground">Exit code</dt>
                <dd
                  className={cn(
                    "font-mono text-xs tabular-nums",
                    // Non-zero is honest and never presented as a pass.
                    didNotComplete &&
                      "font-medium text-red-600 dark:text-red-400",
                  )}
                >
                  {record.exit_code}
                </dd>
              </div>
            </dl>
          </CardContent>
        </Card>
      </section>

      <section aria-label="Provenance">
        <Card>
          <CardHeader>
            <CardTitle>Provenance</CardTitle>
            <CardDescription>
              Hover a hash to see the full value. The record is signed;
              the manifest is invocation metadata, not attested.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <dl className="grid grid-cols-2 gap-x-4 gap-y-3 sm:grid-cols-3">
              <div>
                <dt className="text-xs text-muted-foreground">source_url</dt>
                <dd className="font-mono text-xs break-all">
                  {record.source_url ?? "n/a"}
                </dd>
              </div>
              <div>
                <dt className="text-xs text-muted-foreground">source_commit</dt>
                <dd>
                  {record.source_commit ? (
                    <Hash value={record.source_commit} />
                  ) : (
                    <span className="font-mono text-xs">n/a</span>
                  )}
                </dd>
              </div>
              <div>
                <dt className="text-xs text-muted-foreground">
                  source_tree_sha256
                </dt>
                <dd>
                  {record.source_tree_sha256 ? (
                    <Hash value={record.source_tree_sha256} />
                  ) : (
                    <span className="font-mono text-xs">n/a</span>
                  )}
                </dd>
              </div>
              {manifest?.requested_rev ? (
                <div>
                  <dt className="text-xs text-muted-foreground">
                    requested revision (invocation metadata, not attested)
                  </dt>
                  <dd className="font-mono text-xs">{manifest.requested_rev}</dd>
                </div>
              ) : null}
              <div>
                <dt className="text-xs text-muted-foreground">claims_sha256</dt>
                <dd>
                  <Hash value={record.claims_sha256} />
                </dd>
              </div>
              {record.interpreter ? (
                <div>
                  <dt className="text-xs text-muted-foreground">interpreter</dt>
                  <dd className="font-mono text-xs break-all">
                    {record.interpreter}
                  </dd>
                </div>
              ) : null}
            </dl>
          </CardContent>
        </Card>
      </section>

      <section aria-label="Claims">
        <Card>
          <CardHeader>
            <CardTitle>Claims</CardTitle>
            <CardDescription>
              The paper&apos;s numbers vs. what Contig observed on this machine,
              with the engine&apos;s message verbatim.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <ClaimsTable claims={record.claim_results} />
          </CardContent>
        </Card>
      </section>

      <section aria-label="Repair history">
        <Card>
          <CardHeader>
            <CardTitle>Repair history</CardTitle>
            <CardDescription>
              The bounded detect, diagnose, patch, re-run loop. The applied
              marker appears only when the patch was enacted and the loop
              retried.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {record.repair_history.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                No repairs were needed.
              </p>
            ) : (
              <ol className="relative space-y-4 before:absolute before:top-2 before:bottom-2 before:left-2.5 before:w-px before:bg-border">
                {record.repair_history.map((step) => (
                  <RepairStepCard key={step.attempt} step={step} />
                ))}
              </ol>
            )}
          </CardContent>
        </Card>
      </section>

      <section aria-label="Signature">
        <Card>
          <CardHeader>
            <CardTitle>Signature</CardTitle>
          </CardHeader>
          <CardContent>
            {signature ? (
              <div className="space-y-2">
                <div className="flex flex-wrap items-center gap-2 text-sm">
                  <ShieldCheck className="size-4 text-emerald-600 dark:text-emerald-400" aria-hidden="true" />
                  <span className="font-medium">Signed bundle</span>
                  <Badge variant="outline" className="gap-1 font-mono text-xs">
                    {signature.algo}
                  </Badge>
                  <code className="font-mono text-xs">
                    {signature.public_key.slice(0, 8)}…
                  </code>
                </div>
                <p className="text-xs text-muted-foreground">
                  The bundle&apos;s presence is shown; verification is not
                  computed in this dashboard slice.
                </p>
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">Unsigned bundle</p>
            )}
          </CardContent>
        </Card>
      </section>

      <section aria-label="Bundle downloads">
        <Card>
          <CardHeader>
            <CardTitle>Download bundle</CardTitle>
            <CardDescription>
              The bundle&apos;s JSON files, served as attachments for offline
              audit. The source tree is attested by its commit and tree hash,
              never downloaded.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap items-center gap-2">
              {/* download attribute so the browser saves the file rather than
                  navigating; the route also sets a Content-Disposition. */}
              <a
                href={`${downloadBase}?file=record`}
                download
                className={buttonVariants({ variant: "outline", size: "sm", className: "gap-2" })}
              >
                <FileJson className="size-4" aria-hidden="true" />
                Download record
              </a>
              <a
                href={`${downloadBase}?file=manifest`}
                download
                className={buttonVariants({ variant: "outline", size: "sm", className: "gap-2" })}
              >
                <FileText className="size-4" aria-hidden="true" />
                Download manifest
              </a>
              {signature ? (
                <a
                  href={`${downloadBase}?file=signature`}
                  download
                  className={buttonVariants({ variant: "outline", size: "sm", className: "gap-2" })}
                >
                  <FileKey2 className="size-4" aria-hidden="true" />
                  Download signature
                </a>
              ) : null}
            </div>
          </CardContent>
        </Card>
      </section>
    </div>
  );
}