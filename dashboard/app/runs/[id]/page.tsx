// Run detail view. Server Component: it does the data fetch via getRun and renders
// the verdict plus three tabbed panels (QC, self-heal, provenance). The verdict is
// computed by the engine and read straight off the record, the dashboard never
// re-derives trust.
import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft } from "lucide-react";

import { PageHeader } from "@/components/page-header";
import { InterruptedView } from "@/components/run/interrupted-view";
import { QcPanel } from "@/components/run/qc-panel";
import { ProvenancePanel } from "@/components/run/provenance-panel";
import { RepairTimeline } from "@/components/run/repair-timeline";
import { ReproduceActions } from "@/components/run/reproduce-actions";
import { RunningView } from "@/components/run/running-view";
import { VerdictCard } from "@/components/run/verdict-card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { getLaunchManifest, getRun, getRunState, getRunStatus } from "@/lib/runs";

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
  const record = await getRun(id);
  if (!record) {
    // No bundle yet: a live run shows the polling in-progress view; a run whose
    // process has died (no verdict) is interrupted, not stuck; otherwise 404.
    const state = await getRunState(id);
    if (state === "running") {
      const status = await getRunStatus(id);
      return (
        <RunShell id={id}>
          <RunningView id={id} startedAt={status?.started_at} />
        </RunShell>
      );
    }
    if (state === "interrupted") {
      return (
        <RunShell id={id}>
          <InterruptedView />
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

      {manifest ? <ReproduceActions id={record.run_id} /> : null}

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
