// Run list view (Server Component). Reads run bundles from disk via the data layer
// and hands the records to the client table for sorting and filtering. The fetch
// stays on the server; only the interactive table opts into the client.
import Link from "next/link";
import { GitCompareArrows, Loader2, Plus } from "lucide-react";

import { PageHeader } from "@/components/page-header";
import { RunTestProfileButton } from "@/components/run-test-profile-button";
import { Button } from "@/components/ui/button";
import { listRuns, listRunningRuns } from "@/lib/runs";
import { RunsTable } from "./runs-table";

// Read fresh on every request so the list reflects the current runs on disk.
export const dynamic = "force-dynamic";

export default async function RunsPage() {
  const [runs, running] = await Promise.all([listRuns(), listRunningRuns()]);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Runs"
        count={runs.length}
        description="Every pipeline run that produced a bundle, with its verdict, task outcomes, and whether the self-heal loop had to repair it."
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <Button
              render={<Link href="/runs/new" />}
              size="sm"
              className="gap-2"
            >
              <Plus className="size-4" aria-hidden="true" />
              New run
            </Button>
            <Button
              render={<Link href="/runs/compare" />}
              variant="outline"
              size="sm"
              className="gap-2"
            >
              <GitCompareArrows className="size-4" aria-hidden="true" />
              Compare runs
            </Button>
            <RunTestProfileButton />
          </div>
        }
      />

      {running.length > 0 ? (
        <div className="rounded-xl border bg-card p-4">
          <h2 className="mb-2 text-xs font-medium tracking-wide text-muted-foreground uppercase">
            In progress
          </h2>
          <ul className="space-y-1.5">
            {running.map((r) => (
              <li key={r.run_id} className="flex items-center gap-2 text-sm">
                <Loader2 className="size-4 animate-spin text-brand" aria-hidden="true" />
                <Link
                  href={`/runs/${r.run_id}`}
                  className="font-mono font-medium underline-offset-4 hover:underline"
                >
                  {r.run_id}
                </Link>
                <span className="text-muted-foreground">running</span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

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
