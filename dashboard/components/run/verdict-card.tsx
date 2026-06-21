// Plain-language explanation of a run's verdict. The verdict is computed by the
// engine (a pydantic computed_field) and serialized into the record, so this card
// only explains it, it never re-derives trust. It names what drove the verdict:
// failed tasks (from taskCounts) and the count of fail/warn QC checks.
import { StatusBadge } from "@/components/status-badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { explainVerdict, taskCounts } from "@/lib/derive";
import type { RunRecord, Verdict } from "@/lib/types";

const VERDICT_HEADLINE: Record<Verdict, string> = {
  pass: "Ran to completion and every QC check passed.",
  warn: "Completed, but a QC check is borderline, look before you trust it.",
  fail: "A task failed, or a QC check failed, do not trust the output.",
  unverified:
    "Completed but nothing checked it, so correctness is not claimed.",
};

export function VerdictCard({ record }: { record: RunRecord }) {
  const { total, failed } = taskCounts(record);
  const qcFailed = record.qc_results.filter((q) => q.status === "fail").length;
  const qcWarned = record.qc_results.filter((q) => q.status === "warn").length;
  const qcTotal = record.qc_results.length;

  // Explain the recorded verdict: the one-line reason plus the deciding checks
  // (the checks whose status drove the verdict). This never re-derives trust.
  const explanation = explainVerdict(record);

  // Build the "what drove this verdict" reasons in plain language.
  const drivers: string[] = [];
  if (failed > 0) {
    drivers.push(
      `${failed} of ${total} ${failed === 1 ? "task" : "tasks"} failed`,
    );
  }
  if (qcFailed > 0) {
    drivers.push(
      `${qcFailed} QC ${qcFailed === 1 ? "check" : "checks"} failed`,
    );
  }
  if (qcWarned > 0) {
    drivers.push(
      `${qcWarned} QC ${qcWarned === 1 ? "check" : "checks"} borderline`,
    );
  }
  if (record.verdict === "unverified" && qcTotal === 0) {
    drivers.push("no QC checks ran");
  }
  if (record.verdict === "pass" && drivers.length === 0) {
    drivers.push(
      qcTotal > 0
        ? `all ${qcTotal} QC ${qcTotal === 1 ? "check" : "checks"} passed`
        : "all tasks completed",
    );
  }

  return (
    <Card aria-labelledby="verdict-title" className="gap-0">
      <CardHeader className="gap-3 border-b pb-4">
        <CardTitle
          id="verdict-title"
          className="flex flex-wrap items-center gap-3 text-lg"
        >
          <StatusBadge status={record.verdict} size="lg" />
          <span className="text-muted-foreground text-xs font-medium tracking-wide uppercase">
            Verdict
          </span>
        </CardTitle>
        <CardDescription className="text-base leading-relaxed text-foreground">
          {VERDICT_HEADLINE[record.verdict]}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-5 pt-5">
        {drivers.length > 0 && (
          <div>
            <h3 className="mb-1.5 text-xs font-medium tracking-wide text-muted-foreground uppercase">
              What drove this verdict
            </h3>
            <ul className="list-disc space-y-0.5 pl-5 text-sm">
              {drivers.map((d) => (
                <li key={d}>{d}</li>
              ))}
            </ul>
          </div>
        )}
        <div>
          <h3 className="mb-1.5 text-xs font-medium tracking-wide text-muted-foreground uppercase">
            Decided by
          </h3>
          <p className="text-sm">{explanation.reason}</p>
          {explanation.decidingChecks.length > 0 ? (
            <ul className="mt-2 space-y-1">
              {explanation.decidingChecks.map((c) => (
                <li
                  key={c.check}
                  className="flex flex-wrap items-center gap-2 rounded-lg bg-muted/50 px-3 py-2 text-sm"
                >
                  <StatusBadge status={c.status} />
                  <span className="font-mono text-xs break-all">{c.check}</span>
                  <span className="font-mono text-xs tabular-nums text-muted-foreground">
                    {c.value === null ? "n/a" : c.value}
                    {c.expected_range ? ` vs ${c.expected_range}` : ""}
                  </span>
                </li>
              ))}
            </ul>
          ) : null}
        </div>

        <dl className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          <div className="rounded-lg bg-muted/50 px-3 py-2.5">
            <dt className="text-xs text-muted-foreground">Tasks (failed / total)</dt>
            <dd className="mt-0.5 font-mono text-sm tabular-nums">
              <span className={failed > 0 ? "text-red-600 dark:text-red-400" : ""}>
                {failed}
              </span>{" "}
              / {total}
            </dd>
          </div>
          <div className="rounded-lg bg-muted/50 px-3 py-2.5">
            <dt className="text-xs text-muted-foreground">QC failed / warn</dt>
            <dd className="mt-0.5 font-mono text-sm tabular-nums">
              {qcTotal > 0 ? `${qcFailed} / ${qcWarned}` : "none ran"}
            </dd>
          </div>
          <div className="rounded-lg bg-muted/50 px-3 py-2.5">
            <dt className="text-xs text-muted-foreground">QC checks total</dt>
            <dd className="mt-0.5 font-mono text-sm tabular-nums">{qcTotal}</dd>
          </div>
        </dl>
      </CardContent>
    </Card>
  );
}
