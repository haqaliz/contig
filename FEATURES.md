# Contig Dashboard: Features and 6-Month Roadmap

A researched feature set for the Contig web dashboard (a Next.js app in
`dashboard/`, Tailwind + shadcn/ui, reading run bundles and corpus JSON directly
from disk). This document exists so the founder can choose the roadmap. It does
not commit to building anything yet.

It was produced by a research team that grounded every item in the validated
repo docs (VISION, PRODUCT_SPEC, ARCHITECTURE, MARKET_ANALYSIS, RESEARCH_FINDINGS)
and in the actual built engine under `src/contig/`, plus a competitive scan of
Galaxy, Terra, DNAnexus, Seqera Platform, Latch, and Basepair.

---

## How to read this

- **Phases** are time windows, not commitments: P1 (months 1-2), P2 (months 3-4),
  P3 (months 5-6). Within a phase, features are grouped by theme.
- **Engine column**: "Built" means the data or function already exists in
  `src/contig/` and the dashboard only reads/renders it. "NEW" means net-new
  Python engine work is required first (these are collected in the "Engine work
  required" appendix, because they gate several features and cost backend time).
- **Effort**: S, M, or L, for the dashboard work itself.

### The single most important framing

The competitive scan confirmed the thesis in MARKET_ANALYSIS section 4:
**incumbents own infrastructure and observability, not intelligence.** Every
platform examined is strong at monitoring, QC display, provenance, sharing, and
cost. None issues an output-correctness verdict, none shows a reasoned
self-heal chain, and none has an accumulating failure corpus. So the dashboard
has two jobs:

1. **Table-stakes** (so Contig is not a toy): live monitoring, inline QC,
   provenance, cost, sharing, rerun. We must have these.
2. **Differentiation** (the only reason to switch): the verified verdict, the
   visible detect-to-diagnose-to-patch-to-rerun chain, provable reproducibility,
   and the failure-corpus that compounds. These are the wedge.

The recommended sequencing below front-loads the differentiation that costs
almost no engine work (it is already in the bundle), then earns the table-stakes
that need write paths and live streaming.

---

## Personas (recap, from PRODUCT_SPEC)

- **A, lone computational biologist**: can code, is the lab's single point of
  failure, wants to offload run/debug/verify toil.
- **B, wet-lab scientist who cannot code** (the ~74% with no programming
  experience, arxiv 2507.20122v1): wants data to a trustworthy answer without a
  script they cannot evaluate. Largest TAM, sets the approachability bar.
- **C, core facility**: wants throughput, consistency, and auditable results a
  non-expert PI can trust.
- **D, biotech researcher**: wants defensible provenance and reproducibility.

---

## Competitive landscape (condensed)

| Platform | Dashboard strengths | The Layer-2 gap (what none of them do) |
|---|---|---|
| Galaxy | Live history monitor, inline MultiQC, reproducible Histories (rerun, export) | No autonomous diagnosis, mechanical resubmit only, no correctness verdict |
| Terra (Broad) | Job-history hierarchy, rule-based OOM auto-retry, call caching, per-run cost | Manual log troubleshooting, mechanical retries, no correctness verdict |
| DNAnexus | Live states + failureReason, HTML/IGV viewers, 21 CFR Part 11 audit trail | Failures categorized not diagnosed, plain restart, no correctness verdict |
| Seqera Platform | Real-time monitoring, resolved config, per-task cost, inline MultiQC, resume | Static errorStrategy retry, AI summarizes MultiQC but does not adjudicate correctness |
| Latch | DAG view, live shell, per-process cost, validated sheet input, relaunch | Visibility only, user-initiated relaunch, no correctness verdict |
| Basepair | Publication-quality interactive reports, strong audit trail, reproducible reruns | Static error-code catalog with human KB, no self-heal, no correctness verdict |

**Watch item:** Seqera now markets a "Seqera AI" that claims agents "diagnose root
causes, apply fixes, and restart pipelines automatically"
(seqera.io/platform/seqera-ai). Scope and reliability are unverified from public
docs, and even their copy stops short of a scientific-correctness verdict. This
is the nearest public encroachment on the moat; track it closely.

---

## Phase 1 (Months 1-2): the Run Inspector

A read-only dashboard over finished run bundles, with near-zero engine changes.
It ships fast, is immediately useful, and already delivers the two headline
differentiators just by rendering what the bundle contains. This is the
strongest, most defensible first release.

### Run navigation

| Feature | What it does | Engine | Effort |
|---|---|---|---|
| Run list with verdict badges | All bundles as rows: id, pipeline@revision, verdict badge, task pass/fail counts, repaired flag | Built (workspace, bundle, verdict) | S |
| Filter, search, sort | By verdict, pipeline, assay, failure count; free-text on id/pipeline | Built | S |
| Empty states that teach | Purposeful first screens linking to the bundled smoke run, not blank tables | Frontend only | S |

### The verified verdict (DIFFERENTIATOR)

| Feature | What it does | Engine | Effort |
|---|---|---|---|
| Verdict card, plain language | Renders PASS/WARN/FAIL/UNVERIFIED in jargon-free words, color plus icon plus text | Built (verdict, report) | S |
| Honest-verdict explainer | Explains the reduction and names the exact check(s) that drove it; never reads UNVERIFIED as pass | Shipped 2026-06-22 (explain_verdict, contig show --explain, Decided by section in the verdict card) | S |

### QC surface

| Feature | What it does | Engine | Effort |
|---|---|---|---|
| QC results table | Each QCResult: check, status pill, value, expected range, message; fails sorted to top | Built (qc_results) | S |
| Per-sample QC drill-down | Pivots the `check:sample` key into a sample axis, so you see which library failed | Built (parse only) | M |
| Cross-sample QC panel | Library-size skew, sample count, MAD outliers with cohort context | Built (cross_sample) | S |

### Self-heal transparency (DIFFERENTIATOR)

| Feature | What it does | Engine | Effort |
|---|---|---|---|
| Repair-chain timeline | Per attempt: detect to diagnose to patch to outcome, as a readable story | Built (repair_history) | M |
| Patch detail card | Patch kind, structured operation, rationale, risk tier, expected_signal | Built (repair) | S |
| Diagnosis explainer | root_cause plus matched evidence lines plus confidence; friendly FailureClass labels | Built (detect) | S |
| Repair-outcome banner | Healed, paused for confirmation, or gave up, tied to the verdict | Built (self_heal) | S |

### Provenance and reproduce-bundle

| Feature | What it does | Engine | Effort |
|---|---|---|---|
| Provenance panel | Pipeline@revision, resolved params, container digests, input/output checksums, tool versions | Built (bundle, RunRecord) | M |
| Download the bundle | Zip the on-disk run directory for handoff or archive | Built (write_bundle) | S |
| Raw plus rendered viewer | The human report and the raw run_record.json, each hash copyable | Built (report) | S |
| Reproducibility status header | Verdict plus whether the bundle carries the fields needed to reproduce it | Built | S |

### Moat #2 made visible (read-only)

| Feature | What it does | Engine | Effort |
|---|---|---|---|
| Detector-eval dashboard | Accuracy, per-class precision/recall/support, and the current misses worklist | Built (evaluate_detector) | M |
| "How Contig is learning" panel | Corpus size and classes covered, framed as a trust signal for buyers | Built (corpus) | M |

### Foundation

| Feature | What it does | Engine | Effort |
|---|---|---|---|
| Accessibility baseline | Verdict never color-only, keyboard nav, contrast, screen-reader labels, scalable type | Frontend only | M |

---

## Phase 2 (Months 3-4): Launch and Reproduce

The dashboard starts to act, not just observe: guided intake, triggering runs,
reproducing, diffing, sharing, and surfacing cost. Several items need a write
path or modest engine work (flagged NEW).

### Guided intake and plan-approve

| Feature | What it does | Engine | Effort |
|---|---|---|---|
| Sample-sheet upload plus pre-flight validation | Catches column/duplicate/missing-FASTQ issues before a run starts | Built (samplesheet) | S |
| Data-shape inspection | Inferred sample count, paired/single/mixed, replicate warnings | Built (datashape) | S |
| Reference selection | iGenomes key or local FASTA+GTF, either/or enforced | Built (reference) | S |
| Analysis templates gallery | The curated registry shown as start-from cards (not a blank goal box) | Built (registry) | S |
| Plan-and-approve view | Proposed pipeline, params, rationale, warnings, with an explicit approve gate | Built planner; NEW run-trigger | M |
| First-run onboarding wizard | Data to goal to approved plan, guided, for a non-coder's first session | Built planner; NEW trigger | L |
| Trigger a run from the dashboard | A web entry point that dispatches a planned run | NEW: run-dispatch entrypoint | L |

### Compute and backends

| Feature | What it does | Engine | Effort |
|---|---|---|---|
| Backend selection plus caps | Local vs AWS Batch (queue, region, S3 work dir), memory/CPU/time ceilings, config preview | Built (nfconfig); AWS Batch preflight refuses a misconfigured launch and a runbook lands the live PASS (2026-06-22) | M |
| Backend pre-flight validation | Refuses a misconfigured backend up front with the exact missing-option error | Built (ConfigGenerationError) | S |

### Reproduce, diff, and share

| Feature | What it does | Engine | Effort |
|---|---|---|---|
| One-click re-run from a bundle | Re-execute the same revision, params, and pinned environment, open beside the original | Shipped 2026-06-22 (launch.json manifest, contig rerun, Reproduce exactly plus Edit and relaunch) | L |
| Diff two runs | Side by side on params, revision, digests, QC value deltas, output checksums | Built data; new diff helper | M |
| Export a verified report (HTML/PDF) | Self-contained report (verdict, plan, QC, repair chain, provenance), hashes only, never reads | NEW: HTML/PDF renderer | M |
| Shareable read-only run page | Static export of one run for someone without the dashboard, metadata only | NEW: static export | M |
| Reproducibility badge | Compact embeddable status (verified, repaired, fully pinned) for a README or slide | Built | S |
| Output-integrity re-verification | Re-hash outputs still on disk against output_checksums to prove no drift | Shipped 2026-06-22 (output_checksums captured at finalize; contig verify re-hashes and exits non-zero on drift; dashboard output-integrity badge) | S |

### QC depth

| Feature | What it does | Engine | Effort |
|---|---|---|---|
| "What to look at" on WARN | Ranks offending checks worst-first in plain language (which sample, metric, measured vs expected) | Built data plus copy | M |
| Structural / integrity check view | Output present and non-empty, index present, gzip intact | NEW: wire structural checks into run_qc/bundle | M |

### Cost and resources

| Feature | What it does | Engine | Effort |
|---|---|---|---|
| Resource actuals from the trace | Per-task duration, realtime, peak memory | NEW: keep timings in parse_trace, request mem fields | M |
| Run cost estimate and actuals | Pre-run estimate from samples plus backend plus caps; post-run actuals for the managed tier | NEW: cost model (depends on actuals) | L |

---

## Phase 3 (Months 5-6): Live and Learn

The hardest and most differentiating work: watch runs live, make the corpus
compound through human curation, and prove the detector improves. Most of this
needs real engine work, so it follows once the read and launch surfaces are solid.

### Live monitoring and self-heal-in-flight

| Feature | What it does | Engine | Effort |
|---|---|---|---|
| Live run progress | Tasks submitted/running/succeeded/failed and the current step, updating in real time | Shipped 2026-06-22 (progress.py snapshot from status.json plus trace.txt; contig status/watch; polling dashboard view with a collapsible log tail) | L |
| Self-heal activity feed (live) | The detect-to-patch-to-rerun chain as it happens, with an interactive confirm gate for risky patches | Shipped 2026-06-22 (repair_progress.jsonl appended per attempt, surfaced live; confirm gate: needs_confirmation and destructive patches pause for human approve/reject via pending_approval.json with a 30 minute timeout; contig approve, dashboard Approve/Reject with a destructive double-confirm) | L |
| In-run controls: cancel and resume | Stop a runaway job, resume from the last good checkpoint | Shipped 2026-06-22 (contig cancel kills the process group and writes status cancelled; contig resume re-runs the same id with Nextflow -resume from cached tasks; dashboard Cancel and Resume controls) | M |
| Completion and escalation notifications | In-app first, then email/webhook, on finish, failure, or a decision needing confirmation | Shipped 2026-06-22 (notifications.jsonl events on finished/failed/cancelled/awaiting_approval; contig run --notify webhook; SMTP email via env; dashboard activity bell) | M |

### Corpus curation (the moat compounding)

| Feature | What it does | Engine | Effort |
|---|---|---|---|
| Pending-review labeling tool (WRITE) | Confirm or correct a provisional label, then promote a real-run failure into the golden corpus | NEW: safe write-back/promote, dedupe | L |
| Provisional vs confirmed split view | Browse confirmed golden cases vs still-provisional pending cases, filter by class and source | Built reads | M |
| Corpus growth and coverage metrics | Confirmed cases over time, per-class support, thin-coverage flags | NEW: timestamped append history | M |
| Repair success-rate analytics | Across all runs: auto-healed vs paused vs gave-up, by failure class | Built data; cross-run aggregation | M |
| Recurring failure-pattern clusters | Group by class plus shared log signature to surface systemic failure modes | NEW: signature extraction/clustering | M |

### Detector improvement and model-swap

| Feature | What it does | Engine | Effort |
|---|---|---|---|
| Detector-improvement trend | Accuracy and per-class scores across successive corpus versions | Shipped 2026-06-22 (EvalSnapshot persisted to eval_history.jsonl by contig eval-detector --snapshot and auto on corpus-promote; contig eval-detector --history; accuracy-over-time trend plus per-class deltas on /eval) | L |
| Model-swap comparison harness | Two diagnosers/models over the same frozen corpus, per-class deltas, newly fixed vs newly broken | Shipped 2026-06-22 (pluggable Detector interface + registry, rules and rules-strict detectors, contig eval-detector --detector scores any over the corpus, dashboard /eval detector selector; an LLM detector plugs in behind the same interface later) | L |
| Cross-run verification benchmarking (DIFFERENTIATOR) | Show a pipeline's output matches a validated reference output for that assay | NEW: reference-output validation | L |

### Advanced provenance and guidance

| Feature | What it does | Engine | Effort |
|---|---|---|---|
| Methods-section generator | Draft a citation-ready methods paragraph from the bundle (templating over our own provenance, not workflow authoring) | NEW: templating step | M |
| Audit trail / provenance log | Cross-run chronological view of every agent action and gating event | Built per-run; cross-run aggregation | M |
| Guided escalation prompts | When the engine escalates a genuinely ambiguous decision, present it as a plain question with safe options | NEW: structured escalation format | L |
| RO-Crate / interoperable export | Map the bundle to RO-Crate so provenance interoperates beyond Contig | NEW: schema mapping | L |

---

## Engine work required (cross-cutting)

These are the net-new Python items that gate dashboard features. The founder
should weigh these as backend cost when sequencing, since several high-value
features cannot ship without them. Roughly in dependency order:

1. **Run-dispatch entry point** (trigger a run from the web): unlocks plan-approve,
   onboarding wizard, the whole launch surface.
2. **Structural checks into the bundle**: `verification.structural` exists but is
   not yet wired into `run_qc`, so the integrity view has no data.
3. **Run start timestamp on RunRecord**: needed for date sort and any over-time
   metric.
4. **Output checksum capture**: `output_checksums` is on the model but not
   populated on real runs; gates output-integrity re-verification and full diff.
5. **Resource actuals in trace parsing**: `events.parse_trace_text` keeps only
   process/status/exit; extend to duration/realtime/peak memory.
6. **Re-run entry point** from a RunRecord: gates one-click reproduce.
7. **HTML/PDF and static-export renderers** over RunRecord: gate shareable reports
   and read-only links.
8. **Live status stream** (Nextflow weblog or incremental trace ingestion plus a
   subscribe channel): the single biggest gap, gates all live monitoring and the
   in-flight self-heal feed.
9. **Corpus promote/write-back** (confirm, relabel, dedupe, move pending to
   golden): gates the curation tool, the heart of moat #2 becoming interactive.
10. **Eval-history persistence** and a **pluggable detector provider**: gate the
    improvement trend and the model-swap harness.
11. **Cost model plus backend price table**: gates managed-tier cost actuals.
12. **Structured escalation prompt format** and a **UI-to-engine approval
    callback**: gate guided escalation and the live confirm gate.

---

## Explicit non-goals (strategic guardrails)

Stated so the roadmap does not drift:

- **No Layer-1 workflow authoring as a product surface.** The planner's
  goal-to-pipeline match is a deterministic, replaceable provider surfaced only
  for approval. The methods generator templates over our own provenance; it does
  not write pipelines.
- **No raw-read egress.** Every share/export feature carries only hashes and
  metadata. Genomic reads never leave the user's machine (ARCHITECTURE section 8).
- **Nothing requiring wet-lab or clinical credentials, proprietary biological
  datasets, or EHR/regulatory integration.** Those are outside the founder's edge
  by design.
- **No correctness over-claiming.** UNVERIFIED is never rendered as PASS;
  verifiability claims are scoped honestly per assay type.

---

## Sources

Repo docs: VISION.md, docs/product/PRODUCT_SPEC.md, docs/technical/ARCHITECTURE.md,
docs/business/MARKET_ANALYSIS.md, docs/business/BUSINESS_MODEL.md,
docs/business/GTM.md, docs/RESEARCH_FINDINGS.md, README.md, and the engine under
src/contig/. Competitive product-feature claims are cited from each vendor's own
documentation in the research notes; no market-size or statistical numbers were
invented. Figures referenced (the ~74% no-programming and BixBench ~17%) come
from the repo docs, not from this exercise.
