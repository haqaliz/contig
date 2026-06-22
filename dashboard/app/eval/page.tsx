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
import { PageHeader } from "@/components/page-header";
import { EvalView } from "@/components/eval/eval-view";
import { EvalHistory } from "@/components/eval/eval-history";
import { getDetectorEval, getEvalHistory } from "@/lib/runs";

// Re-run the detector eval on every request (it shells out to the CLI). The
// history is read straight from the committed jsonl, independent of the live CLI.
export const dynamic = "force-dynamic";

export default async function EvalPage() {
  const [report, history] = await Promise.all([
    getDetectorEval(),
    getEvalHistory(),
  ]);

  if (!report) {
    // The live eval CLI is unavailable, but the recorded history still stands on
    // its own, so we show the trend (or its empty state) below the notice.
    return (
      <div className="flex flex-col gap-8">
        <PageHeader
          title="Detector eval"
          description="How Contig is learning: the failure detector scored against the labeled corpus of known failures."
        />

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Terminal className="size-4 text-muted-foreground" aria-hidden="true" />
              Live eval not available
            </CardTitle>
            <CardDescription>
              The live detector eval could not be produced because the{" "}
              <code className="font-mono">contig eval-detector</code> CLI was
              unavailable.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">
              The eval runs from the repo root (one level up from this dashboard).
              Once the CLI can run there, this page will show the detector&apos;s
              accuracy, per-class scores, and current misses. The recorded trend
              below comes from the committed history and is shown regardless.
            </p>
          </CardContent>
        </Card>

        <EvalHistory history={history} />
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-8">
      <EvalView report={report} />
      <EvalHistory history={history} />
    </div>
  );
}
