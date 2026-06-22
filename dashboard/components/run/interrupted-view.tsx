// Shown when a run started but its process stopped before producing a verdict
// (the machine restarted, or the toolchain failed to start). It is not stuck
// "running" and does not block new runs. The run dir survives, so we offer Resume
// (re-run the same run id with -resume, reusing cached tasks) alongside starting
// a fresh run.
import { AlertTriangle } from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";
import { ButtonLink } from "@/components/ui/button";
import { ResumeButton } from "@/components/run/resume-button";

export function InterruptedView({ id }: { id: string }) {
  return (
    <Card>
      <CardContent className="flex flex-col items-center gap-3 py-12 text-center">
        <span className="flex size-12 items-center justify-center rounded-full bg-amber-50 text-amber-700 dark:bg-amber-950 dark:text-amber-300">
          <AlertTriangle className="size-6" aria-hidden="true" />
        </span>
        <div className="space-y-1">
          <p className="text-base font-medium">This run was interrupted</p>
          <p className="max-w-prose text-sm text-muted-foreground">
            It started but stopped before producing a verdict (the process or
            machine stopped). No bundle was written. You can resume it (Contig
            reuses the cached tasks) or start a fresh run.
          </p>
        </div>
        <div className="mt-1 flex flex-col items-center gap-2">
          <ResumeButton id={id} size="sm" />
          <ButtonLink href="/runs/new" variant="ghost" size="sm">
            Start a new run instead
          </ButtonLink>
        </div>
      </CardContent>
    </Card>
  );
}
