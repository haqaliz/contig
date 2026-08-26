// Third-party `contig reproduce` listing (Server Component). Reads reproduce
// bundles from disk via the data layer and hands the records to the client
// table for sorting and filtering. The fetch stays on the server; only the
// interactive table opts into the client. Read-only: there is no launch form --
// `contig reproduce` executes an arbitrary shell command on the user's compute,
// so the CLI remains the launch surface; this page only shows how.
import { PageHeader } from "@/components/page-header";
import { listReproduceRuns } from "@/lib/reproduce";
import { ReproduceTable } from "./reproduce-table";

// Read fresh on every request so the list reflects the bundles on disk.
export const dynamic = "force-dynamic";

export default async function ReproducePage() {
  const runs = await listReproduceRuns();

  return (
    <div className="space-y-6">
      <PageHeader
        title="Reproductions"
        count={runs.length}
        description="Every third-party contig reproduce bundle on this machine, with its derived overall status and per-claim counts."
      />

      {runs.length === 0 ? (
        <div className="rounded-xl border border-dashed p-10 text-center">
          <h2 className="text-base font-medium">No reproductions yet</h2>
          <p className="mx-auto mt-2 max-w-prose text-sm text-muted-foreground">
            Reproductions appear here once <code className="font-mono">contig
            reproduce</code> writes a{" "}
            <code className="font-mono">reproduce_record.json</code> under the
            runs directory, next to your first-party run bundles.
          </p>
          <p className="mx-auto mt-3 max-w-prose text-sm text-muted-foreground">
            If you have already run one, check that{" "}
            <code className="font-mono">CONTIG_RUNS_DIR</code> points at the
            right directory.
          </p>
        </div>
      ) : (
        <ReproduceTable records={runs} />
      )}

      <div className="rounded-xl border bg-card p-5">
        <h2 className="text-sm font-medium">
          How to reproduce a published paper
        </h2>
        <p className="mt-2 max-w-2xl text-sm text-muted-foreground">
          From a checkout of the paper&apos;s repository, run{" "}
          <code className="font-mono text-xs">
            contig reproduce &lt;repo&gt; --run &quot;&lt;cmd&gt;&quot; --claims
            &lt;file&gt;
          </code>{" "}
          to re-run the analysis and check each quantitative claim against what
          Contig observes. Pull the claims out of the paper first with{" "}
          <code className="font-mono text-xs">contig extract-claims</code>.
        </p>
        <p className="mt-2 max-w-2xl text-sm text-muted-foreground">
          Verdicts compare the paper&apos;s numbers against what Contig observed
          on this machine — research-use computation, never a paper&apos;s
          conclusions. A repo that commits its outputs is read honestly as{" "}
          <code className="font-mono text-xs">unverified</code>: the outputs
          were not rewritten by this run, so nothing was corroborated.
        </p>
      </div>
    </div>
  );
}