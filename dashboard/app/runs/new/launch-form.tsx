"use client";

// The real-data launch form: data -> plan -> approve -> launch. The user
// describes a goal and points at a sample sheet, previews a plan (which the
// engine produces and the user approves), then launches a real run on their
// compute. Launch is gated on a fresh, successful plan preview so a user can
// never launch a stale plan: editing any field clears the stored plan.
import { useState } from "react";
import { useRouter } from "next/navigation";
import { ChevronDown, ChevronRight, Loader2, Play, Sparkles } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import type { Plan } from "@/lib/types";

type ReferenceMode = "genome" | "files";

export function LaunchForm() {
  const router = useRouter();

  // Form state.
  const [goal, setGoal] = useState("");
  const [input, setInput] = useState("");
  const [referenceMode, setReferenceMode] = useState<ReferenceMode>("genome");
  const [genome, setGenome] = useState("");
  const [fasta, setFasta] = useState("");
  const [gtf, setGtf] = useState("");
  const [maxMemory, setMaxMemory] = useState("");
  const [maxCpus, setMaxCpus] = useState("");
  const [capsOpen, setCapsOpen] = useState(false);

  // Plan + request state. `plan` is the approved-pending plan: when it is set
  // (and matches the current inputs, which we guarantee by clearing it on every
  // edit), the launch button is enabled.
  const [plan, setPlan] = useState<Plan | null>(null);
  const [planError, setPlanError] = useState<string | null>(null);
  const [launchError, setLaunchError] = useState<string | null>(null);
  const [previewing, setPreviewing] = useState(false);
  const [launching, setLaunching] = useState(false);

  const busy = previewing || launching;

  // Any edit invalidates a previously previewed plan, so the user cannot launch
  // a plan that no longer reflects the form. Errors are cleared too.
  function invalidatePlan() {
    setPlan(null);
    setPlanError(null);
    setLaunchError(null);
  }

  // The reference fields we send depend on the active mode only, so switching
  // mode does not smuggle stale values from the other mode into a request.
  function referencePayload() {
    if (referenceMode === "genome") {
      return { genome: genome.trim() || undefined };
    }
    return {
      fasta: fasta.trim() || undefined,
      gtf: gtf.trim() || undefined,
    };
  }

  async function preview() {
    setPreviewing(true);
    setPlan(null);
    setPlanError(null);
    setLaunchError(null);
    try {
      const res = await fetch("/api/runs/plan", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          goal: goal.trim(),
          input: input.trim(),
          ...referencePayload(),
        }),
      });
      const data = (await res.json()) as { plan?: Plan; error?: string };
      if (res.ok && data.plan) {
        setPlan(data.plan);
        return;
      }
      setPlanError(data.error ?? "Could not build a plan.");
    } catch {
      setPlanError("Could not build a plan.");
    } finally {
      setPreviewing(false);
    }
  }

  async function launch() {
    if (!plan) return;
    setLaunching(true);
    setLaunchError(null);
    try {
      const res = await fetch("/api/runs/launch", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          input: input.trim(),
          pipeline: plan.pipeline,
          ...referencePayload(),
          maxMemory: maxMemory.trim() || undefined,
          maxCpus: maxCpus.trim() || undefined,
        }),
      });
      const data = (await res.json()) as { run_id?: string; error?: string };
      if (res.ok && data.run_id) {
        router.push(`/runs/${data.run_id}`);
        return;
      }
      setLaunchError(data.error ?? "Could not launch the run.");
    } catch {
      setLaunchError("Could not launch the run.");
    } finally {
      setLaunching(false);
    }
  }

  return (
    <div className="space-y-6">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void preview();
        }}
        className="space-y-5"
      >
        <div className="space-y-2">
          <label htmlFor="goal" className="text-sm font-medium text-foreground">
            Goal
          </label>
          <Input
            id="goal"
            value={goal}
            onChange={(e) => {
              setGoal(e.target.value);
              invalidatePlan();
            }}
            placeholder="RNA-seq differential expression"
            disabled={busy}
          />
          <p className="text-xs text-muted-foreground">
            Describe what you want from the data, in plain language.
          </p>
        </div>

        <div className="space-y-2">
          <label htmlFor="input" className="text-sm font-medium text-foreground">
            Sample sheet path
          </label>
          <Input
            id="input"
            value={input}
            onChange={(e) => {
              setInput(e.target.value);
              invalidatePlan();
            }}
            placeholder="/data/samplesheet.csv"
            className="font-mono"
            disabled={busy}
          />
          <p className="text-xs text-muted-foreground">
            A path on this machine. The FASTQs it references must exist locally.
          </p>
        </div>

        <fieldset className="space-y-3">
          <legend className="text-sm font-medium text-foreground">Reference</legend>
          <div
            role="radiogroup"
            aria-label="Reference mode"
            className="inline-flex rounded-lg border border-input p-0.5"
          >
            <button
              type="button"
              role="radio"
              aria-checked={referenceMode === "genome"}
              onClick={() => {
                setReferenceMode("genome");
                invalidatePlan();
              }}
              disabled={busy}
              className="rounded-md px-3 py-1 text-sm font-medium transition-colors outline-none focus-visible:ring-2 focus-visible:ring-ring/50 disabled:opacity-50 aria-checked:bg-muted aria-checked:text-foreground text-muted-foreground"
            >
              iGenomes key
            </button>
            <button
              type="button"
              role="radio"
              aria-checked={referenceMode === "files"}
              onClick={() => {
                setReferenceMode("files");
                invalidatePlan();
              }}
              disabled={busy}
              className="rounded-md px-3 py-1 text-sm font-medium transition-colors outline-none focus-visible:ring-2 focus-visible:ring-ring/50 disabled:opacity-50 aria-checked:bg-muted aria-checked:text-foreground text-muted-foreground"
            >
              FASTA + GTF
            </button>
          </div>

          {referenceMode === "genome" ? (
            <div className="space-y-2">
              <label
                htmlFor="genome"
                className="text-sm font-medium text-foreground"
              >
                iGenomes key
              </label>
              <Input
                id="genome"
                value={genome}
                onChange={(e) => {
                  setGenome(e.target.value);
                  invalidatePlan();
                }}
                placeholder="GRCh38"
                className="font-mono"
                disabled={busy}
              />
            </div>
          ) : (
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="space-y-2">
                <label
                  htmlFor="fasta"
                  className="text-sm font-medium text-foreground"
                >
                  FASTA path
                </label>
                <Input
                  id="fasta"
                  value={fasta}
                  onChange={(e) => {
                    setFasta(e.target.value);
                    invalidatePlan();
                  }}
                  placeholder="/ref/genome.fa"
                  className="font-mono"
                  disabled={busy}
                />
              </div>
              <div className="space-y-2">
                <label
                  htmlFor="gtf"
                  className="text-sm font-medium text-foreground"
                >
                  GTF path
                </label>
                <Input
                  id="gtf"
                  value={gtf}
                  onChange={(e) => {
                    setGtf(e.target.value);
                    invalidatePlan();
                  }}
                  placeholder="/ref/genes.gtf"
                  className="font-mono"
                  disabled={busy}
                />
              </div>
            </div>
          )}
        </fieldset>

        <div className="rounded-lg border border-input">
          <button
            type="button"
            onClick={() => setCapsOpen((v) => !v)}
            aria-expanded={capsOpen}
            className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm font-medium text-muted-foreground outline-none transition-colors hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring/50"
          >
            {capsOpen ? (
              <ChevronDown className="size-4" aria-hidden="true" />
            ) : (
              <ChevronRight className="size-4" aria-hidden="true" />
            )}
            Resource caps (optional)
          </button>
          {capsOpen ? (
            <div className="grid gap-3 px-3 pb-3 sm:grid-cols-2">
              <div className="space-y-2">
                <label
                  htmlFor="maxMemory"
                  className="text-sm font-medium text-foreground"
                >
                  Max memory
                </label>
                <Input
                  id="maxMemory"
                  value={maxMemory}
                  onChange={(e) => {
                    setMaxMemory(e.target.value);
                    invalidatePlan();
                  }}
                  placeholder="6.GB"
                  className="font-mono"
                  disabled={busy}
                />
              </div>
              <div className="space-y-2">
                <label
                  htmlFor="maxCpus"
                  className="text-sm font-medium text-foreground"
                >
                  Max cpus
                </label>
                <Input
                  id="maxCpus"
                  value={maxCpus}
                  onChange={(e) => {
                    setMaxCpus(e.target.value);
                    invalidatePlan();
                  }}
                  placeholder="2"
                  className="font-mono"
                  disabled={busy}
                />
              </div>
            </div>
          ) : null}
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <Button type="submit" variant="outline" disabled={busy}>
            {previewing ? (
              <Loader2 className="size-4 animate-spin" aria-hidden="true" />
            ) : (
              <Sparkles className="size-4" aria-hidden="true" />
            )}
            Preview plan
          </Button>
          <Button type="button" onClick={() => void launch()} disabled={busy || !plan}>
            {launching ? (
              <Loader2 className="size-4 animate-spin" aria-hidden="true" />
            ) : (
              <Play className="size-4" aria-hidden="true" />
            )}
            Launch run
          </Button>
          {!plan ? (
            <span className="text-xs text-muted-foreground">
              Preview a plan to enable launch.
            </span>
          ) : null}
        </div>

        {planError ? (
          <p
            role="alert"
            className="rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive"
          >
            {planError}
          </p>
        ) : null}
      </form>

      {plan ? (
        <Card>
          <CardHeader>
            <CardTitle className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
              <span className="font-mono break-all">
                {plan.pipeline} @ {plan.revision}
              </span>
              <span className="text-xs font-normal tracking-wide text-muted-foreground uppercase">
                {plan.assay}
              </span>
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <p className="text-sm text-muted-foreground">{plan.rationale}</p>

            {plan.warnings.length > 0 ? (
              <ul className="space-y-2">
                {plan.warnings.map((warning, i) => (
                  <li
                    key={i}
                    className="rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-200"
                  >
                    {warning}
                  </li>
                ))}
              </ul>
            ) : null}

            <Separator />

            <div className="space-y-1.5">
              <h3 className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
                Parameters
              </h3>
              {Object.keys(plan.params).length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  No parameters set.
                </p>
              ) : (
                <dl className="grid gap-x-4 gap-y-1 sm:grid-cols-[max-content_1fr]">
                  {Object.entries(plan.params).map(([key, value]) => (
                    <div
                      key={key}
                      className="grid grid-cols-subgrid sm:col-span-2"
                    >
                      <dt className="font-mono text-sm text-muted-foreground">
                        {key}
                      </dt>
                      <dd className="font-mono text-sm break-all text-foreground">
                        {String(value)}
                      </dd>
                    </div>
                  ))}
                </dl>
              )}
            </div>
          </CardContent>
        </Card>
      ) : null}

      {launchError ? (
        <p
          role="alert"
          className="rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive"
        >
          {launchError}
        </p>
      ) : null}
    </div>
  );
}
