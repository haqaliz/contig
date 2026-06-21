// Run list view (Server Component). Reads run bundles from disk via the data layer
// and hands the records to the client table for sorting and filtering. The fetch
// stays on the server; only the interactive table opts into the client.
import Link from "next/link";
import { GitCompareArrows } from "lucide-react";

import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { listRuns } from "@/lib/runs";
import { RunsTable } from "./runs-table";

// Read fresh on every request so the list reflects the current runs on disk.
export const dynamic = "force-dynamic";

export default async function RunsPage() {
  const runs = await listRuns();

  return (
    <div className="space-y-6">
      <PageHeader
        title="Runs"
        count={runs.length}
        description="Every pipeline run that produced a bundle, with its verdict, task outcomes, and whether the self-heal loop had to repair it."
        actions={
          <Button
            render={<Link href="/runs/compare" />}
            variant="outline"
            size="sm"
            className="gap-2"
          >
            <GitCompareArrows className="size-4" aria-hidden="true" />
            Compare runs
          </Button>
        }
      />

      {runs.length === 0 ? (
        <div className="rounded-xl border border-dashed p-10 text-center">
          <h2 className="text-base font-medium">No runs yet</h2>
          <p className="mx-auto mt-2 max-w-prose text-sm text-muted-foreground">
            Runs appear here once <code className="font-mono">contig run</code>{" "}
            produces a bundle (a <code className="font-mono">run_record.json</code>{" "}
            under the runs directory). Try the bundled smoke run to get a first
            record on disk, then refresh this page.
          </p>
          <p className="mx-auto mt-3 max-w-prose text-sm text-muted-foreground">
            If you have already run a pipeline, check that{" "}
            <code className="font-mono">CONTIG_RUNS_DIR</code> points at the right
            directory.
          </p>
          <p className="mt-4 text-sm">
            <Link href="/eval" className="underline underline-offset-4">
              See the detector eval
            </Link>{" "}
            while you wait.
          </p>
        </div>
      ) : (
        <RunsTable runs={runs} />
      )}
    </div>
  );
}
