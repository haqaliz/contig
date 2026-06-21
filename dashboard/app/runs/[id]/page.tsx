// Run detail view. Server Component: it does the data fetch via getRun and renders
// the verdict plus three tabbed panels (QC, self-heal, provenance). The verdict is
// computed by the engine and read straight off the record, the dashboard never
// re-derives trust.
import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft } from "lucide-react";

import { StatusBadge } from "@/components/status-badge";
import { QcPanel } from "@/components/run/qc-panel";
import { ProvenancePanel } from "@/components/run/provenance-panel";
import { RepairTimeline } from "@/components/run/repair-timeline";
import { VerdictCard } from "@/components/run/verdict-card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { getRun } from "@/lib/runs";

export default async function RunDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const record = await getRun(id);
  if (!record) {
    notFound();
  }

  const qcCount = record.qc_results.length;
  const repairCount = record.repair_history.length;

  return (
    <main className="mx-auto w-full max-w-5xl space-y-6 px-4 py-8">
      <Link
        href="/runs"
        className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="size-4" aria-hidden="true" />
        All runs
      </Link>

      <header className="space-y-2">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="font-mono text-2xl font-semibold break-all">
            {record.run_id}
          </h1>
          <StatusBadge status={record.verdict} size="lg" />
        </div>
        <p className="font-mono text-sm text-muted-foreground break-all">
          {record.pipeline} @ {record.pipeline_revision}
        </p>
      </header>

      <VerdictCard record={record} />

      <Tabs defaultValue="qc">
        <TabsList>
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
    </main>
  );
}
