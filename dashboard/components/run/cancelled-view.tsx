// Shown when a run was cancelled by a human (status.json state "cancelled"). It
// is a terminal state, but the run dir and its Nextflow work cache survive, so we
// offer Resume: re-run the same run id with -resume and reuse the cached tasks.
import { Ban } from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";
import { ResumeButton } from "@/components/run/resume-button";

export function CancelledView({ id }: { id: string }) {
  return (
    <Card>
      <CardContent className="flex flex-col items-center gap-3 py-12 text-center">
        <span className="flex size-12 items-center justify-center rounded-full bg-muted text-muted-foreground">
          <Ban className="size-6" aria-hidden="true" />
        </span>
        <div className="space-y-1">
          <p className="text-base font-medium">This run was cancelled</p>
          <p className="max-w-prose text-sm text-muted-foreground">
            You stopped this run before it produced a verdict. The work it had
            already completed is cached, so you can resume it: Contig re-runs the
            same run id and reuses the finished tasks.
          </p>
        </div>
        <div className="mt-1">
          <ResumeButton id={id} size="sm" />
        </div>
      </CardContent>
    </Card>
  );
}
