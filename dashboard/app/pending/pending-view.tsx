// The pending-review view. It renders the auto-captured failure cases that the
// detector stashed with a PROVISIONAL label. These are NOT in the golden corpus
// yet: a human confirms or corrects each label, then promotes it (the per-case
// actions are a client component), so the eval is never graded against the
// detector's own guesses.
import { FlaskConical, Inbox } from "lucide-react";

import { PageHeader } from "@/components/page-header";
import { PendingCaseActions } from "@/components/pending/pending-case-actions";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import type { FailureCase, TaskEvent } from "@/lib/types";

/** A TaskEvent is "failing" if it did not exit cleanly (non-zero or null exit). */
function isFailing(event: TaskEvent): boolean {
  return event.exit !== 0;
}

/** The distinct process names of the failing events, in first-seen order. */
function failingProcessNames(events: TaskEvent[]): string[] {
  const seen = new Set<string>();
  const names: string[] = [];
  for (const event of events) {
    if (isFailing(event) && !seen.has(event.process)) {
      seen.add(event.process);
      names.push(event.process);
    }
  }
  return names;
}

function PendingCard({ pendingCase }: { pendingCase: FailureCase }) {
  const failingCount = pendingCase.events.filter(isFailing).length;
  const processes = failingProcessNames(pendingCase.events);
  const log = pendingCase.log_text.trim();

  return (
    <Card>
      <CardHeader className="border-b pb-4">
        <CardTitle className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between sm:gap-4">
          <span className="font-mono text-sm break-all">{pendingCase.case_id}</span>
          <span className="flex items-center gap-2 text-xs font-normal text-muted-foreground">
            <span>provisional label</span>
            <Badge
              variant="outline"
              className="gap-1 font-mono font-medium border-amber-300 bg-amber-50 text-amber-900 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-300"
            >
              <FlaskConical className="size-3" aria-hidden="true" />
              <span>{pendingCase.expected_class}</span>
            </Badge>
          </span>
        </CardTitle>
      </CardHeader>

      <CardContent className="flex flex-col gap-4 pt-1">
        {pendingCase.description ? (
          <p className="text-sm text-muted-foreground">{pendingCase.description}</p>
        ) : null}

        <dl className="grid grid-cols-1 gap-x-6 gap-y-3 text-sm sm:grid-cols-2">
          <div className="flex flex-col gap-0.5">
            <dt className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
              Source
            </dt>
            <dd className="font-mono break-all">{pendingCase.source}</dd>
          </div>
          <div className="flex flex-col gap-0.5">
            <dt className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
              Failing events
            </dt>
            <dd className="tabular-nums">
              {failingCount} of {pendingCase.events.length}
            </dd>
          </div>
        </dl>

        {processes.length > 0 ? (
          <div className="flex flex-col gap-1.5">
            <span className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
              Failing processes
            </span>
            <ul className="flex flex-wrap gap-1.5">
              {processes.map((name) => (
                <li key={name}>
                  <Badge variant="outline" className="font-mono">
                    {name}
                  </Badge>
                </li>
              ))}
            </ul>
          </div>
        ) : null}

        <div className="flex flex-col gap-1.5">
          <span className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
            Log excerpt
          </span>
          {log.length > 0 ? (
            <pre className="max-h-64 overflow-auto rounded-md bg-muted p-3 font-mono text-xs leading-relaxed whitespace-pre-wrap text-foreground/90">
              {log}
            </pre>
          ) : (
            <p className="text-sm text-muted-foreground">No log text was captured.</p>
          )}
        </div>

        <Separator />
        <div className="flex flex-col gap-2">
          <span className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
            Review
          </span>
          <PendingCaseActions
            caseId={pendingCase.case_id}
            provisional={pendingCase.expected_class}
          />
        </div>
      </CardContent>
    </Card>
  );
}

export function PendingView({ cases }: { cases: FailureCase[] }) {
  const description =
    "Auto-captured failures from real runs, each stashed with a PROVISIONAL label from the detector. A human confirms or corrects the label before it is promoted into the golden corpus, so the eval never grades the detector against its own guesses.";

  if (cases.length === 0) {
    return (
      <div className="flex flex-col gap-6">
        <PageHeader title="Pending review" description={description} />

        <Card>
          <CardContent className="flex flex-col items-center gap-3 py-12 text-center">
            <span className="flex size-12 items-center justify-center rounded-full bg-emerald-50 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300">
              <Inbox className="size-6" aria-hidden="true" />
            </span>
            <h2 className="text-base font-medium">Nothing waiting for review</h2>
            <p className="max-w-prose text-sm text-muted-foreground">
              There are no pending cases right now. When a real run fails, its
              failure case will be captured here with a provisional label, ready for
              a human to confirm before it joins the golden corpus.
            </p>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <PageHeader title="Pending review" count={cases.length} description={description} />

      <ul className="flex flex-col gap-4">
        {cases.map((pendingCase) => (
          <li key={pendingCase.case_id}>
            <PendingCard pendingCase={pendingCase} />
          </li>
        ))}
      </ul>

      <Separator />

      <footer className="text-sm text-muted-foreground">
        Confirm a label to promote the case into the golden corpus, or correct it
        first. Promoted cases are scored by the detector eval, so the corpus (and
        the detector) compound from real runs.
      </footer>
    </div>
  );
}
