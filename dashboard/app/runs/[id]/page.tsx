// Run detail view. Server Component: it does the data fetch via getRun and renders
// the verdict plus three tabbed panels (QC, self-heal, provenance). The verdict is
// computed by the engine and read straight off the record, the dashboard never
// re-derives trust.
import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft } from "lucide-react";

import { PageHeader } from "@/components/page-header";
import { CancelledView } from "@/components/run/cancelled-view";
import { InterruptedView } from "@/components/run/interrupted-view";
import { OutputIntegrityCard } from "@/components/run/output-integrity-card";
import { QcPanel } from "@/components/run/qc-panel";
import { ProvenancePanel } from "@/components/run/provenance-panel";
import { RepairTimeline } from "@/components/run/repair-timeline";
import { ReproduceActions } from "@/components/run/reproduce-actions";
import { ResourceCostCard } from "@/components/run/resource-cost-card";
import { RunningView } from "@/components/run/running-view";
import { VerdictCard } from "@/components/run/verdict-card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { currentViewer } from "@/lib/auth0";
import {
  getLaunchManifest,
  getRun,
  getRunCost,
  getRunState,
  getRunStatus,
} from "@/lib/runs";
import { RunExportActions } from "@/components/run/run-export-actions";

// A running run has no bundle yet, so always read fresh.
export const dynamic = "force-dynamic";

function RunShell({ id, children }: { id: string; children: React.ReactNode }) {
  return (
    <div className="mx-auto w-full max-w-5xl space-y-6">
      <Link
        href="/runs"
        className="inline-flex items-center gap-1 rounded-sm text-sm text-muted-foreground transition-colors hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none"
      >
        <ArrowLeft className="size-4" aria-hidden="true" />
        All runs
      </Link>
      <PageHeader title={id} titleClassName="font-mono break-all" />
      {children}
    </div>
  );
}

export default async function RunDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  // Per-user isolation (PRD contract E): a run this viewer may not see reads as
  // absent, so the page 404s rather than leaking another user's run. An admin
  // (and the dev/test bypass) sees every run.
  const viewer = await currentViewer();
  const record = await getRun(id, viewer);
  if (!record) {
    // No bundle yet: a live or paused run shows the polling in-progress view (the
    // view itself surfaces the approval gate when paused); a cancelled run offers
    // resume; a run whose process has died (no verdict) is interrupted, not
    // stuck; otherwise 404.
    const state = await getRunState(id);
    if (state === "running" || state === "awaiting_approval") {
      const status = await getRunStatus(id);
      return (
        <RunShell id={id}>
          <RunningView id={id} startedAt={status?.started_at} />
        </RunShell>
      );
    }
    if (state === "cancelled") {
      return (
        <RunShell id={id}>
          <CancelledView id={id} />
        </RunShell>
      );
    }
    if (state === "interrupted") {
      return (
        <RunShell id={id}>
          <InterruptedView id={id} />
        </RunShell>
      );
    }
    notFound();
  }

  const qcCount = record.qc_results.length;
  const repairCount = record.repair_history.length;
  // Reproduce is offered only when the run wrote a launch manifest (older runs
  // predate it). It rebuilds the exact run, or opens a pre-filled launch form.
  const manifest = await getLaunchManifest(id);
  // The cost at the default rates (zero, so the default total is zero). The card
  // lets the user enter rates to recompute. Only worth fetching when the run
  // actually recorded per-task resource usage.
  const resourceUsage = record.resource_usage ?? [];
  const initialCost =
    resourceUsage.length > 0 ? await getRunCost(record.run_id) : null;

  return (
    <div className="mx-auto w-full max-w-5xl space-y-6">
      <Link
        href="/runs"
        className="inline-flex items-center gap-1 rounded-sm text-sm text-muted-foreground transition-colors hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none"
      >
        <ArrowLeft className="size-4" aria-hidden="true" />
        All runs
      </Link>

      <PageHeader
        title={record.run_id}
        titleClassName="font-mono break-all"
        description={
          <span className="font-mono break-all">
            {record.pipeline} @ {record.pipeline_revision}
          </span>
        }
      />

      <VerdictCard record={record} />

      <OutputIntegrityCard
        id={record.run_id}
        outputCount={Object.keys(record.output_checksums).length}
      />

      {resourceUsage.length > 0 ? (
        <ResourceCostCard
          id={record.run_id}
          resourceUsage={resourceUsage}
          initialCost={initialCost}
        />
      ) : null}

      {manifest ? <ReproduceActions id={record.run_id} /> : null}

      <RunExportActions id={record.run_id} />

      <Tabs defaultValue="qc" className="gap-4">
        <TabsList className="w-full justify-start sm:w-fit">
          <TabsTrigger value="qc">QC ({qcCount})</TabsTrigger>
          <TabsTrigger value="self-heal">Self-heal ({repairCount})</TabsTrigger>
          <TabsTrigger value="provenance">Provenance</TabsTrigger>
        </TabsList>
        <TabsContent value="qc">
          <QcPanel qcResults={record.qc_results} />
        </TabsContent>
        <TabsContent value="self-heal">
          <RepairTimeline history={record.repair_history} />
        </TabsContent>
        <TabsContent value="provenance">
          <ProvenancePanel record={record} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
