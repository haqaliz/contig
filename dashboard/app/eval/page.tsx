// The detector eval page. Server Component: it does the data fetch (shelling out
// to the Python `contig eval-detector` CLI via getDetectorEval) and hands the
// report to the view. If the CLI is unavailable the fetch returns null and we
// degrade gracefully instead of erroring.
import { Terminal } from "lucide-react";

import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card";
import { EvalView } from "@/components/eval/eval-view";
import { getDetectorEval } from "@/lib/runs";

// Re-run the detector eval on every request (it shells out to the CLI).
export const dynamic = "force-dynamic";

export default async function EvalPage() {
  const report = await getDetectorEval();

  if (!report) {
    return (
      <div className="flex flex-col gap-6">
        <header className="flex flex-col gap-1">
          <h1 className="font-heading text-2xl font-semibold tracking-tight">
            Detector eval
          </h1>
          <p className="text-sm text-muted-foreground">
            How Contig is learning: the failure detector scored against the labeled
            corpus of known failures.
          </p>
        </header>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Terminal className="size-4 text-muted-foreground" aria-hidden="true" />
              Eval not available
            </CardTitle>
            <CardDescription>
              The detector eval could not be produced because the{" "}
              <code className="font-mono">contig eval-detector</code> CLI was
              unavailable.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">
              The eval runs from the repo root (one level up from this dashboard).
              Once the CLI can run there, this page will show the detector&apos;s
              accuracy, per-class scores, and current misses.
            </p>
          </CardContent>
        </Card>
      </div>
    );
  }

  return <EvalView report={report} />;
}
