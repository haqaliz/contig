"use client";

// Output integrity for a finished run (PRD contract B). A run records a sha256
// for each output file; this card lets a user re-hash those files on disk and
// see whether they still match. The dashboard never hashes anything itself: the
// Verify button POSTs to /api/runs/[id]/verify, which shells `contig verify <id>
// --json`, and we render the {ok, changed, missing} report it returns.
//
// Three resting states, by what the record carries:
//   not captured  the run recorded no output checksums, so there is nothing to
//                 verify (a neutral badge, never a pass or a fail).
//   uncaptured-on-disk path: with checksums recorded but not yet checked, the
//                 badge invites a verify.
// After a verify: "outputs verified" (ok) or "drift detected" (changed/missing).
import { useState } from "react";
import {
  ShieldCheck,
  ShieldAlert,
  ShieldQuestion,
  BadgeCheck,
  BadgeAlert,
  Loader2,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { cn } from "@/lib/utils";
import type { OutputVerification } from "@/lib/types";

type Phase = "idle" | "verifying" | "verified" | "error";

export function OutputIntegrityCard({
  id,
  outputCount,
}: {
  id: string;
  outputCount: number;
}) {
  const captured = outputCount > 0;
  const [phase, setPhase] = useState<Phase>("idle");
  const [report, setReport] = useState<OutputVerification | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function verify() {
    setPhase("verifying");
    setError(null);
    try {
      const res = await fetch(
        `/api/runs/${encodeURIComponent(id)}/verify`,
        { method: "POST" },
      );
      if (res.ok) {
        setReport((await res.json()) as OutputVerification);
        setPhase("verified");
        return;
      }
      const data = (await res.json().catch(() => ({}))) as { error?: string };
      setError(data.error ?? "Could not verify the outputs.");
      setPhase("error");
    } catch {
      setError("Could not verify the outputs.");
      setPhase("error");
    }
  }

  // The badge reflects the strongest known signal. Before a verify it states
  // whether outputs were captured at all; after one it states the result.
  const drift =
    phase === "verified" &&
    report !== null &&
    (!report.ok || report.changed.length > 0 || report.missing.length > 0);
  const verifiedOk = phase === "verified" && report !== null && !drift;

  // Signed-record status (PRD contracts E, F), known only after a verify since the
  // signature check rides on the same report. `signed` true with `signature_ok`
  // true is a verified signature; signed but not ok is a tamper warning. A run with
  // no signature.json leaves `signed` absent, so no badge is shown.
  const signed = phase === "verified" && report?.signed === true;
  const signatureOk = signed && report?.signature_ok === true;
  const tampered = signed && report?.signature_ok !== true;

  return (
    <Card aria-labelledby="integrity-title">
      <CardHeader className="gap-3 border-b pb-4">
        <CardTitle
          id="integrity-title"
          className="flex flex-wrap items-center gap-3 text-lg"
        >
          {verifiedOk ? (
            <Badge
              variant="outline"
              className="gap-1 border-emerald-300 bg-emerald-50 px-3 py-1 text-sm font-medium text-emerald-800 dark:border-emerald-800 dark:bg-emerald-950 dark:text-emerald-300"
            >
              <ShieldCheck className="size-4" aria-hidden="true" />
              Outputs verified
            </Badge>
          ) : drift ? (
            <Badge
              variant="outline"
              className="gap-1 border-red-300 bg-red-50 px-3 py-1 text-sm font-medium text-red-800 dark:border-red-900 dark:bg-red-950 dark:text-red-300"
            >
              <ShieldAlert className="size-4" aria-hidden="true" />
              Drift detected
            </Badge>
          ) : !captured ? (
            <Badge
              variant="outline"
              className="gap-1 border-slate-300 bg-slate-50 px-3 py-1 text-sm font-medium text-slate-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300"
            >
              <ShieldQuestion className="size-4" aria-hidden="true" />
              Not captured
            </Badge>
          ) : (
            <Badge
              variant="outline"
              className="gap-1 border-slate-300 bg-slate-50 px-3 py-1 text-sm font-medium text-slate-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300"
            >
              <ShieldQuestion className="size-4" aria-hidden="true" />
              Not yet verified
            </Badge>
          )}
          {signatureOk ? (
            <Badge
              variant="outline"
              className="gap-1 border-emerald-300 bg-emerald-50 px-3 py-1 text-sm font-medium text-emerald-800 dark:border-emerald-800 dark:bg-emerald-950 dark:text-emerald-300"
            >
              <BadgeCheck className="size-4" aria-hidden="true" />
              Signed, signature verified
            </Badge>
          ) : tampered ? (
            <Badge
              variant="outline"
              className="gap-1 border-red-300 bg-red-50 px-3 py-1 text-sm font-medium text-red-800 dark:border-red-900 dark:bg-red-950 dark:text-red-300"
            >
              <BadgeAlert className="size-4" aria-hidden="true" />
              Signature mismatch
            </Badge>
          ) : null}
          <span className="text-muted-foreground text-xs font-medium tracking-wide uppercase">
            Output integrity
          </span>
        </CardTitle>
        <CardDescription className="text-base leading-relaxed text-foreground">
          {verifiedOk
            ? "Every recorded output file re-hashed to its recorded checksum. The outputs on disk match the run."
            : drift
              ? "At least one recorded output no longer matches its checksum, or has gone missing. The outputs on disk differ from the run."
              : !captured
                ? "This run recorded no output checksums, so there is nothing to verify on disk."
                : `This run recorded ${outputCount} output ${outputCount === 1 ? "checksum" : "checksums"}. Re-hash the files on disk to confirm they still match.`}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4 pt-5">
        {captured ? (
          <div className="flex flex-wrap items-center gap-3">
            <Button
              type="button"
              variant="outline"
              onClick={() => void verify()}
              disabled={phase === "verifying"}
            >
              {phase === "verifying" ? (
                <Loader2 className="size-4 animate-spin" aria-hidden="true" />
              ) : (
                <ShieldCheck className="size-4" aria-hidden="true" />
              )}
              {phase === "verified" ? "Verify again" : "Verify outputs"}
            </Button>
            {phase === "error" && error ? (
              <p role="alert" className="text-sm text-destructive">
                {error}
              </p>
            ) : null}
          </div>
        ) : null}

        {signed ? (
          <p
            className={cn(
              "text-sm",
              signatureOk ? "text-muted-foreground" : "text-destructive",
            )}
            role={signatureOk ? undefined : "alert"}
          >
            {signatureOk
              ? "This run carries a detached Ed25519 signature over its content hash, and that signature verified against the recorded bundle."
              : "This run carries a signature, but it did not verify against the recorded bundle. The record may have been altered after signing."}
          </p>
        ) : null}

        {drift && report ? (
          <div className="space-y-3">
            {report.changed.length > 0 ? (
              <DriftList
                title="Changed"
                files={report.changed}
                hint="re-hashed to a different value than recorded"
              />
            ) : null}
            {report.missing.length > 0 ? (
              <DriftList
                title="Missing"
                files={report.missing}
                hint="recorded by the run but no longer on disk"
              />
            ) : null}
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}

function DriftList({
  title,
  files,
  hint,
}: {
  title: string;
  files: string[];
  hint: string;
}) {
  return (
    <div>
      <h3 className="mb-1.5 text-xs font-medium tracking-wide text-muted-foreground uppercase">
        {title} ({files.length}){" "}
        <span className="font-normal normal-case">{hint}</span>
      </h3>
      <ul className="space-y-1">
        {files.map((f) => (
          <li
            key={f}
            className={cn(
              "rounded-lg bg-muted/50 px-3 py-2 font-mono text-xs break-all",
            )}
          >
            {f}
          </li>
        ))}
      </ul>
    </div>
  );
}
