// The detector eval page. Server Component: it does the data fetch (shelling out
// to the Python `contig eval-detector --detector <name>` CLI via getDetectorEval)
// and hands the report to the view. If the CLI is unavailable the fetch returns
// null and we degrade gracefully instead of erroring.
//
// NEXT 16: searchParams is a Promise and must be awaited. The ?detector= query
// chooses which registered detector to score; an unknown value falls back to the
// default "rules" so the CLI is never handed a name outside the registry.
import { Terminal } from "lucide-react";

import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card";
import { PageHeader } from "@/components/page-header";
import { DetectorSelector } from "@/components/eval/detector-selector";
import { DetectorCompare } from "@/components/eval/detector-compare";
import { EvalView } from "@/components/eval/eval-view";
import { EvalHistory } from "@/components/eval/eval-history";
import {
  DETECTOR_NAMES,
  getDetectorEval,
  getEvalHistory,
  isDetectorName,
} from "@/lib/runs";

// Re-run the detector eval on every request (it shells out to the CLI). The
// history is read straight from the committed jsonl, independent of the live CLI.
export const dynamic = "force-dynamic";

export default async function EvalPage({
  searchParams,
}: {
  searchParams: Promise<{ detector?: string }>;
}) {
  const { detector } = await searchParams;
  // Constrain the query to a known detector before it reaches the CLI; anything
  // else falls back to the default so the page never shells an unknown name.
  const selected = isDetectorName(detector) ? detector : "rules";

  const [report, history] = await Promise.all([
    getDetectorEval(selected),
    getEvalHistory(),
  ]);

  const selector = (
    <DetectorSelector detectors={DETECTOR_NAMES} selected={selected} />
  );

  if (!report) {
    // The live eval CLI is unavailable, but the recorded history still stands on
    // its own, so we show the trend (or its empty state) below the notice.
    return (
      <div className="flex flex-col gap-8">
        <PageHeader
          title="Detector eval"
          description="How Contig is learning: the failure detector scored against the labeled corpus of known failures."
        />

        {selector}

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

        <DetectorCompare history={history} />
        <EvalHistory history={history} />
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-8">
      <EvalView report={report} selector={selector} />
      <DetectorCompare history={history} />
      <EvalHistory history={history} />
    </div>
  );
}
