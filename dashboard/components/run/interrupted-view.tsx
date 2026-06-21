// Shown when a run started but its process stopped before producing a verdict
// (cancelled, the machine restarted, or the toolchain failed to start). It is not
// stuck "running" and does not block new runs; the user can start a fresh one.
import { AlertTriangle } from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import Link from "next/link";

export function InterruptedView() {
  return (
    <Card>
      <CardContent className="flex flex-col items-center gap-3 py-12 text-center">
        <span className="flex size-12 items-center justify-center rounded-full bg-amber-50 text-amber-700 dark:bg-amber-950 dark:text-amber-300">
          <AlertTriangle className="size-6" aria-hidden="true" />
        </span>
        <div className="space-y-1">
          <p className="text-base font-medium">This run was interrupted</p>
          <p className="max-w-prose text-sm text-muted-foreground">
            It started but stopped before producing a verdict (it may have been
            cancelled, or the process or machine stopped). No bundle was written.
            You can start a new run.
          </p>
        </div>
        <Button render={<Link href="/runs/new" />} size="sm" className="mt-1">
          Start a new run
        </Button>
      </CardContent>
    </Card>
  );
}
