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
| Trigger a run from the dashboard | A web entry point that dispatches a planned run | Shipped 2026-06-21 (Run test profile, the data to plan to launch form, live progress, cancel/resume/approve) | L |

### Compute and backends

| Feature | What it does | Engine | Effort |
|---|---|---|---|
| Backend selection plus caps | Local vs AWS Batch vs SLURM (queue/partition, account, work dir), memory/CPU/time ceilings, config preview | Built (nfconfig); AWS Batch and SLURM each have a preflight that refuses a misconfigured launch and a runbook; SLURM validated live single-node on 2026-06-23 (nf-core/rnaseq, 234 tasks via sbatch, 0 failed, verdict WARN, identical to the local backend) | M |
| Second workflow engine (Snakemake) | Run a Snakemake workflow through the same run, capture, verify, reproduce engine | Shipped 2026-06-23 (engine-adapter foundation: contig run --engine snakemake --snakefile, ingested into the same RunRecord; proves engine-agnosticism) | L |
| Backend pre-flight validation | Refuses a misconfigured backend up front with the exact missing-option error | Built (ConfigGenerationError) | S |

### Reproduce, diff, and share

| Feature | What it does | Engine | Effort |
|---|---|---|---|
| One-click re-run from a bundle | Re-execute the same revision, params, and pinned environment, open beside the original | Shipped 2026-06-22 (launch.json manifest, contig rerun, Reproduce exactly plus Edit and relaunch) | L |
| Diff two runs | Side by side on params, revision, digests, QC value deltas, output checksums | Built data; new diff helper | M |
| Export a verified report (HTML/PDF) | Self-contained report (verdict, plan, QC, repair chain, provenance), hashes only, never reads | Shipped 2026-06-23 (contig show --html: polished, self-contained, print-to-PDF report incl structural QC and the signature status; dashboard Download report button) | M |
| Shareable read-only run page | Static export of one run for someone without the dashboard, metadata only | Shipped 2026-06-23 (the self-contained HTML report is the shareable artifact; hash it, sign it, email it) | M |
| Reproducibility badge | Compact embeddable status (verified, repaired, fully pinned) for a README or slide | Built | S |
| Output-integrity re-verification | Re-hash outputs still on disk against output_checksums to prove no drift | Shipped 2026-06-22 (output_checksums captured at finalize; contig verify re-hashes and exits non-zero on drift; dashboard output-integrity badge) | S |

### QC depth

| Feature | What it does | Engine | Effort |
|---|---|---|---|
| "What to look at" on WARN | Ranks offending checks worst-first in plain language (which sample, metric, measured vs expected) | Built data plus copy | M |
| Structural / integrity check view | Output present and non-empty, index present, gzip intact | Shipped 2026-06-23 (verification/structural.py: per-assay expected-output manifest, present/non-empty/index/gzip/BAM-integrity/count checks wired into run_qc; a missing or corrupt required output FAILs the verdict; grouped on the dashboard QC panel) | M |
| Signed, tamper-evident run records | Cryptographically sign the bundle so a shared provenance record is verifiably unmodified | Shipped 2026-06-23 (Ed25519: contig keygen, CONTIG_SIGNING_KEY signs at write into signature.json, contig verify checks it and reports signed/signature_ok; dashboard signed badge) | L |

### Cost and resources

| Feature | What it does | Engine | Effort |
|---|---|---|---|
| Resource actuals from the trace | Per-task duration, realtime, peak memory | Shipped 2026-06-23 (RunRecord.resource_usage parsed from the trace; per-task duration, peak RSS, and cpu on the run page) | M |
| Run cost estimate and actuals | Pre-run estimate from samples plus backend plus caps; post-run actuals for the managed tier | Shipped 2026-06-23 (contig cost for post-run actuals; contig estimate for a pre-run runtime and cost estimate, data-driven from past runs of the same pipeline with a sample-count heuristic fallback, shown on the launch form) | L |

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
| Pending-review labeling tool (WRITE) | Confirm or correct a provisional label, then promote a real-run failure into the golden corpus | Shipped 2026-06-21 (contig corpus-promote + the dashboard Pending review: confirm/correct a label, dedupe, write into the golden corpus) | L |
| Provisional vs confirmed split view | Browse confirmed golden cases vs still-provisional pending cases, filter by class and source | Built reads | M |
| Corpus growth and coverage metrics | Confirmed cases over time, per-class support, thin-coverage flags | Shipped 2026-06-23 (contig coverage: per-class support, thin-coverage flags under 3 cases, by-source counts, confirmed-over-time from the eval history; dashboard coverage panel) | M |
| Repair success-rate analytics | Across all runs: auto-healed vs paused vs gave-up, by failure class | **Shipped (Unreleased)** — `contig repair-stats`: per-step outcome-family and failure-class counts plus a per-run unattended-completion rate that states its own denominator. Three-state on both under-determined axes: `patch_applied` key presence (read / legacy-derived / unknown, since `models.py:322` defaults `False` and pydantic cannot distinguish an absent key) and attendance (`approved_and_retried` also fires under `--auto-approve`, which is never persisted). Zero-event and attendance-unknown runs are excluded from both sides of the rate and the exclusions are printed. Read-only over existing bundles — no new instrumentation | M |
| Recurring failure-pattern clusters | Group by class plus shared log signature to surface systemic failure modes | Shipped 2026-06-23 (contig clusters: groups cases by failure class plus a normalized log signature that strips paths/numbers/hashes/timestamps, worst-first; dashboard clusters view) | M |

### Detector improvement and model-swap

| Feature | What it does | Engine | Effort |
|---|---|---|---|
| Detector-improvement trend | Accuracy and per-class scores across successive corpus versions | Shipped 2026-06-22 (EvalSnapshot persisted to eval_history.jsonl by contig eval-detector --snapshot and auto on corpus-promote; contig eval-detector --history; accuracy-over-time trend plus per-class deltas on /eval) | L |
| Model-swap comparison harness | Two diagnosers/models over the same frozen corpus, per-class deltas, newly fixed vs newly broken | Shipped 2026-06-22, extended 2026-06-23 (pluggable Detector interface + registry: rules, rules-strict, and an optional provider-agnostic llm detector (Claude or OpenAI via env); contig eval-detector --detector scores any over the corpus; dashboard /eval detector selector) | L |
| Cross-run verification benchmarking (DIFFERENTIATOR) | Show a pipeline's output matches a validated reference output for that assay | Shipped 2026-06-23 (contig benchmark set designates a reference run per pipeline/assay; contig benchmark compares a run's QC metrics within a relative tolerance plus structural shape, reporting match or drift; dashboard benchmark card) | L |

### Advanced provenance and guidance

| Feature | What it does | Engine | Effort |
|---|---|---|---|
| Methods-section generator | Draft a citation-ready methods paragraph from the bundle (templating over our own provenance, not workflow authoring) | Shipped 2026-06-23 (contig methods: deterministic citation-ready paragraph from the bundle, no LLM; dashboard download button) | M |
| Audit trail / provenance log | Cross-run chronological view of every agent action and gating event | Built per-run; cross-run aggregation | M |
| Guided escalation prompts | When the engine escalates a genuinely ambiguous decision, present it as a plain question with safe options | Shipped 2026-06-23 (when a self-heal decision is ambiguous the gate offers ranked options; contig approve --choose N, or a choice list in the dashboard, picks one) | L |
| RO-Crate / interoperable export | Map the bundle to RO-Crate so provenance interoperates beyond Contig | Shipped 2026-06-23 (contig export --rocrate: an RO-Crate ro-crate-metadata.json with the run as a Dataset, the pipeline as a SoftwareApplication, inputs/outputs as Files with checksums; dashboard download button) | L |

---

## Next: the engine capability track (separate from the dashboard)

The phases above are the **dashboard** roadmap, and they are largely shipped. The
*tool's* next six months are about deepening the engine's scientific and execution
capability: making the verdict harder to fool, recovering more failures without a
human, and widening what we can verify. That work has its own sequenced backlog in
[`docs/technical/CAPABILITY_ROADMAP.md`](docs/technical/CAPABILITY_ROADMAP.md),
built one capability at a time, test-first:

| ID | Capability | Window | What it adds |
|----|-----------|--------|--------------|
| **C1** | Cross-tool concordance verification | **Shipped v0.2.0 + RNA-seq slice (Unreleased) + somatic slice (Unreleased)** | A second independent tool corroborates the result; a verdict axis distinct from the shipped reference-run benchmark (germline slice via `contig verify --concordance-vcf`; RNA-seq slice via `contig verify --concordance-counts` — per-gene Spearman, fraction-agreeing, informational gene-overlap; somatic slice auto in the verdict — `somatic_site_overlap`, the PASS-site Jaccard of Mutect2 vs Strelka2 from one sarek run, no user input; auto-run second germline/RNA tool + single-cell deferred) |
| **C2** | Self-heal breadth plus auto resource-scaling | M2 to M3 (**detector work-dir threading shipped (Unreleased): `read_task_errors` now takes the run's configured `ExecutionTarget.work_dir` as a REQUIRED argument (`run_dir` removed, no dead fallback) instead of globbing `<run_dir>/work`, which is only the default -- so any `--work-dir` had left the detector blind to every `.command.err`, leaving exit-137 OOM as the ONLY classifiable failure, `propose_patches` returning `[]`, and each case filed to the corpus evidence-less, mislabelled, and collapsed into one constant `normalize_signature` cluster; a remote (`s3://`) work dir now yields a self-labelled salient-token note instead of `""`, and both halves of the diagnosis log expression were made raise-safe; closes C2 deferral item (a); honest limits: push not demand-pull, reasoned not observed, and AWS Batch stays structurally undiagnosable -- the limit is made visible, not fixed; resource-aware + single-file missing-index family incl. `.dict` shipped; chr-prefix GTF harmonization shipped; per-contig alias harmonization shipped; directory-shaped STAR index build+redirect shipped, classic BWA + bwa-mem2 detector+corpus-only (v0.11.0); alignment-format detector-only slice shipped (Unreleased) — `alignment_format_mismatch`, the input-format-conversion class's second half (CRAM→BAM repair deferred, no live trigger); peak-RSS-informed OOM memory scaling shipped (Unreleased); walltime-informed `time_limit` scaling shipped (Unreleased); **opt-in heartbeat stall watchdog shipped (Unreleased)**; bwa-mem2/classic-BWA build+redirect + assembly-signature + wider catalog pending) | Bounded OOM/walltime retries up to an absolute ceiling with honest `gave_up_at_ceiling` give-up; an OOM retry is now **sized to the failed task's observed peak RSS** from the run's own trace (`ceil(peak_rss_mb/1024×1.5)` GB) instead of a blind `×2`, with an honest blind fallback when no usable peak exists and the observed peak recorded to `RepairStep.detail`; a `time_limit` retry is now **symmetrically sized to the longest observed `realtime`** (`ceil(max_realtime/3600×1.5)` h) but **floored at the blind `×2`** — a walltime kill's realtime is a censored lower bound, so it ties blind in the common case and only wins in the tail (a trace realtime above the current limit), shipped mostly as a field instrument with a revisit trigger; a missing single-file index is now built and retried — `.fai` (`samtools faidx`), `.bai` (`samtools index`), `.tbi` (`tabix -p vcf`), `.csi` (`bcftools index`), and a GATK sequence dictionary `.dict` (`samtools dict`, resolving the companion FASTA) — with honest `index_unresolvable`/`index_build_failed` give-up and a build-once-per-path guard; a chr-prefix GTF naming mismatch (FASTA `chr1…` vs GTF `1…`, or vice versa) is now auto-harmonized at pre-flight into a run-scoped scratch copy (user file untouched), wrong-assembly still refused, decision recorded in the manifest and `ReferenceIdentity`, WARN breadcrumb on the verdict; the harmonizer now also resolves a **general per-contig alias map** looked up against the actual FASTA contig set — mitochondrion `M`↔`MT` is universal, plus a curated extensible GRCh38 scaffold table (`contig_aliases.tsv`, from UCSC chromAlias) — covering the residual case where autosomes already match but the mito spelling differs, refusing a non-injective rename (no silent contig merge), with the breadcrumb enumerating any unmatched contigs, provenance-only capture; a missing/version-incompatible **STAR** directory-shaped index is now rebuilt with `STAR --runMode genomeGenerate` into a run-scoped scratch dir and the retry is redirected at it (`built_index_and_retried`, bounded to one rebuild per run, STAR version recorded, reproduce re-derives without baking in the scratch path); classic **BWA** and **bwa-mem2** missing-index failures are detected and classified `missing_index` with a golden corpus case each, but build/redirect is deferred with no live trigger (nf-core/sarek auto-builds a missing bwa-mem2 index, iGenomes ships classic BWA, and Contig has no flag to supply a broken index); BAM/CRAM `.csi`, bwa-mem2/classic-BWA build+redirect, corrupt/partial STAR signature, assembly-signature form of reference mismatch, exhaustive per-assembly alias-table completeness, and the wider catalog (format, pin conflict) deferred; **the five inert repair strategies are now resolved (Unreleased) — four made honest advisories, one genuinely enacted.** `disk_full`, `permission_denied`, `conda_solve_failed` and `platform_unsupported` no longer claim a machine action nothing performs: `propose_patches` now emits `kind="advisory"` for each, withdrawing the four inert operations (`clean_work_dir`, `fix_permissions`, `relax_or_pin_env`, `use_native_arch_backend`) rather than reassigning them, and the loop branches on `kind == "advisory"` **before** the applier (`apply_patch` raises if one ever reaches it — defensive, unreachable in practice). An approved advisory now records the deliberately observational `advisory_acknowledged_and_retried` with `patch_applied=False` and `recovered=False` — the recovery is attributed to the human, which is what actually happened — and the approval gate stops serializing an `operation` dict for work Contig will not do, showing guidance and evidence instead; under `--auto-approve` (no human in the loop) an advisory now `gave_up` honestly with the rationale and **no retry**, closing the door the PRD flagged as re-entering the same lie unattended. `container_unavailable` — the one class with a sound premise — now **genuinely waits** its `wait_seconds` through an injected clock seam threaded through `self_heal_run` and `heal.py`, so a downed Docker daemon gets a real pause before retry instead of a silently dropped field. `heal-guard` `covered_classes` moved **11 → 15** (`platform_unsupported` stays deliberately uncovered — reaching it needs a failed event with `exit is None`, but `AttemptSpec.exit` is a required `int` used as both the trace column and the executor return code, a mechanism change out of scope here), guarded outcome-match held at **1.0** over 20 scenarios, `heal_baseline.json` refrozen as a deliberate act. The pinning guard that reddened on any change (`test_five_inert_patch_operations_are_still_consumed_by_nothing`) is retired deliberately and replaced by one pinning the new contract: no advisory carries a withdrawn operation key, and `wait_seconds` is consumed. **Read honestly, against our own interest:** this is push, not demand-pull — **0 of 20** pending-corpus cases and **0 of 15** real runs were ever diagnosed into any of these five classes (the only classes ever diagnosed in the field remain `oom`, `tool_crash`, `missing_index`, `unknown`); `eval-guard` **cannot move and did not** (nothing here touches a detector or corpus, and the pending-corpus append happens before `propose`, so proposer changes write zero bytes to it) — unmoved at 92.3%; the informational `recovery_rate` move (9/16 → 10/20) is **corpus composition**, not loop behaviour, and stays never-guarded; every scenario is self-graded (we authored the fixtures we then grade), with no real nf-core run in CI; and **this recovers nothing new for a user** except a transient Docker-daemon blip. A committed revisit trigger runs in both directions: if the next 20 diagnosed failures contain no case in any of these five classes, the advisory abstraction is restated as taxonomy-only and no further breadth is built on push alone; if `container_unavailable`'s wait fires and does not recover it, the wait is removed rather than lengthened. Two incidental defects found in the dig are filed, not fixed, in `CAPABILITY_ROADMAP.md`'s C2 deferral list: `read_task_errors` goes blind on a custom `--work-dir`, and `risk="destructive"` is a no-op to the engine (only the dashboard honors it); and a **hung** run — which never exits, never raises, and so never reached the detector at all — can now be terminated by an **opt-in** heartbeat watchdog (`--detect-stalls`, `--stall-timeout`, default 1 h, **off by default**): a run counts as alive if `trace.txt`, `.nextflow.log`, **or** `run.log` moved, so a healthy-but-slow long task is never touched; all three silent for the full window means SIGTERM → 5 s grace → SIGKILL over the child's own process group (Nextflow's JVM and tool children, not just the launcher), with the watchdog's verdict written to `run.log` first so the retry is diagnosed `no_progress` — reachable by the detector for the first time, ahead of the OOM check because an exit-137 trace row from a dying Nextflow would otherwise win on the events alone — and retried with `-resume` under `--max-attempts`, ending in an honest `gave_up` rather than a dressed-up recovery; `--stall-timeout` without `--detect-stalls` is refused, not ignored; **honest limits:** no real Contig run has ever been observed to hang (the gap was architectural, the frequency is unmeasured), the 1-hour window is reasoned and **not calibrated**, the terminate mechanics are exercised against real child processes but a real **Nextflow's** SIGTERM exit code and trace contents are reasoned and manual-gated, a failing observer degrades to "no progress observed" (a deliberate trade — a timeout is evidence about the run, an exception is not), Nextflow is the only tested engine, and the settings are deliberately **not** persisted to the launch manifest (a stall is a property of the machine, not the analysis) — which is precisely why the same two flags are accepted by `run`, `rerun` **and** `resume`, since they must be passed on each invocation rather than replayed, and resuming a run that just stalled is exactly when the watchdog is wanted; all three share one validator, refuse identically, and validate before any filesystem work |
| **C3** | Biological-plausibility verification | **Shipped v0.3.0** (germline) **+ RNA-seq (v0.6.0) + single-cell ingestion (Unreleased) + germline sex-check (Unreleased) + RNA-seq mapping-composition (Unreleased) + germline variant-count (Unreleased) + germline plausibility FAIL-severity (Unreleased) + somatic empty-call-set FAIL floor (Unreleased) + RNA-seq plausibility ingestion fix (Unreleased) + verdict-neutral informational checks (Unreleased)** | Assay-aware sanity scoped honestly per assay (germline Ti/Tv, het/hom, and variant-count from the VCF — now with a gross-implausibility **FAIL** gate on WES-safe bands (a noise-level Ti/Tv, a grossly-off het/hom, or an empty call set FAILs the verdict; verdict-only — exit code unchanged by default, opt-in via `--fail-on-verdict`; engineering tripwire, not a clinical claim), plus karyotypic sex-check; RNA-seq `duplication_rate` now correctly keyed to MultiQC's actual `PERCENT_DUPLICATION` and its real 0-1 fraction unit — it had never once fired under its old lowercase/0-100 key, and ships informational-only (no band by design, since a deep/high-input library legitimately exceeds 90% duplication) — plus `rrna_contamination` (still a guessed `percent_rRNA` slug, WARN-capped, no default machine-readable source exists) plus exonic/intronic/unassigned read-composition parsed from RSeQC `read_distribution.txt` (the composition fractions aren't in MultiQC general-stats, so a dedicated gate reads the artifact directly — WARN-capped, UNVERIFIED-when-absent); single-cell cell-QC — recovered cells, median genes/cell, fraction reads in cells — now *fires* by parsing the aligner's own artifact (STARsolo `Summary.csv` / Cell Ranger `metrics_summary.csv`), where before the pack silently no-oped because the metrics never reached MultiQC; default simpleaf degrades to UNVERIFIED; somatic `somatic_variant_count` now **FAILs** on an empty call set (`fail_below: 1`, the direct mirror of the germline floor; 1–9 records still WARN, no `fail_above`); mito-fraction, doublet, gene-body-coverage deferred; **somatic-VAF and RNA-seq FAIL severity declined by design, not deferred** — tumor VAF's expected value depends on purity/clonality the engine never observes, and every RNA-seq extreme is a legitimate protocol, so no calibration fixes either; annotation-pack FAIL severity is a separate C7 item, still deferred; **informational checks are now verdict-neutral** — a check that cannot fail (`duplication_rate`, `gene_symbol_concordance`, `x_het_ratio`, `gene_overlap`) is marked `informational` and excluded from the positive-severity reduction, so a run resting only on informational/unverified checks reduces to `unverified`, never a manufactured `pass`; defensive, changed no real run's verdict) |
| **C4** | New assay, depth-first: somatic variant calling | **Shipped v0.13.0** (intake→launch→verify) **+ VAF plausibility slice (Unreleased) + Strelka2-native VAF slice (Unreleased) + empty-call-set FAIL floor (Unreleased) + swapped-pair smell-test slice (Unreleased)** | A somatic tumor–normal assay end to end on nf-core/sarek: explicit persisted `--assay` (fixes the shared-pipeline collision), sarek tumor/normal sample-sheet pre-flight, `--tools strelka,mutect2` launch seam, structural manifest + methods label; plus a C3-style biological verdict — `median_vaf` + `somatic_variant_count` (WARN-capped) + `pon_applied` from the tumor column of the Mutect2 VCF, UNVERIFIED-when-uncomputable; plus `strelka_median_vaf` (WARN-capped), derived independently from Strelka2's own tier1 counts (`AU`/`CU`/`GU`/`TU` for SNVs, `TAR`/`TIR` for indels) and firing alongside Mutect2's `median_vaf` as cross-caller corroboration; plus a C1 cross-tool concordance axis — `somatic_site_overlap`, the PASS-site Jaccard of the run's Mutect2 vs Strelka2 call sets, auto-run in the verdict with no user input; plus an empty-call-set FAIL floor — `somatic_variant_count fail_below: 1`, so a 0-record call set now **FAILs** the verdict (1–9 records still WARN; deliberately no `fail_above`, a hypermutator or WGS tumor legitimately exceeds the soft `100000` ceiling; reaches the exit code only under the opt-in `--fail-on-verdict`); **VAF/PON FAIL severity declined by design, not deferred** — tumor VAF's expected value is a function of purity/clonality the engine never observes (a low median VAF is legitimate low-purity/subclonal science), `strelka_median_vaf` is bounded to [0,1] given non-negative tier counts so a ceiling would be dead code, and `pon_applied` is a non-numeric 3-state string that never enters `evaluate()`; plus `normal_median_vaf` (WARN-capped, `warn_above: 0.30`), the tumor/normal swapped-pair smell test — median VAF over the Mutect2 VCF's NORMAL column via a new `##normal_sample=` resolver that never guesses a column, flagging a possible swap, mislabel, or tumor-in-normal contamination when the normal carries an implausibly high VAF, UNVERIFIED-when-uncomputable (a smell, not a determination: all three causes give the same number, and the call-set-depleting form of a swap is already caught by the empty-call-set floor); PON reference wiring deferred |
| **C5** | Reference and input-data integrity | M5 (reference-identity **capture** slice shipped; mismatch detector + known-sites + GTF version + RO-Crate pending) | Record reference identity into provenance — explicit FASTA/GTF `sha256` or the iGenomes key (never a fabricated hash), rendered in `contig methods` and the provenance panel; deepens reproduce and seeds C2's mismatch repair. Catching wrong-reference runs at pre-flight is the next slice |
| **C6** | Eval flywheel as a continuous loop | **Slice 1 + slice 2 shipped (Unreleased)** — detector held-out guard + repair-loop outcome-match guard, both wired into CI; **the accuracy trend over versions has SHIPPED** (`holdout_history.jsonl` + `heal_history.jsonl`, `--snapshot`/`--history` on both guards, and the dashboard's `holdout-history.tsx` / `heal-history.tsx` cards — this row previously still called it pending, which was stale); **the C1/C3 fold-in has SHIPPED (Unreleased)** — a labeled verification corpus (`verify_corpus_holdout.jsonl`) + `contig verify-guard` (verdict-match regression guard wired into CI) + a real-run capture/promote channel (`verify-case-promote`), with the honest scope that the guarded number starts synthetic and self-graded and only becomes non-tautological as real runs get labeled; **the reproduce fold-in has SHIPPED (Unreleased)** — `contig reproduce-guard`, the fourth guard, replays 14 frozen scenarios through the **real** reproduce loop (scripted executor/installer seams only) and guards outcome-match at a committed baseline of **13/14 (92.9%)** with one deliberate known-miss, wired into CI — same honest scope: synthetic and self-graded, reproduce-outcome capture/promote still pending | A frozen held-out corpus (`detector_corpus_holdout.jsonl`, 12 cases **at slice 1**; 13 today) and `contig eval-guard` fail the build when the `rules` detector's held-out accuracy drops below a committed baseline (`holdout_baseline.json`, pinning corpus sha/detector/version); `--update-baseline` refreezes it deliberately; loud sha/detector-mismatch warnings; an improvement nudge. **At slice 1** that read honestly 0.833 (10/12), with `qc_anomaly`/`no_progress` structurally unreachable by the detector and left as headroom (superseded — see the current numbers at the end of this row). **Slice 2** adds `contig heal-guard`: a `HealScenario` driver (`heal.py`) replays a frozen `heal_scenarios.jsonl` (7 synthetic cases) through the **real** self-heal loop (detector and `propose` never stubbed) and fails the build when the loop's **outcome-match rate** (right `FailureClass` *and* the declared terminal outcome) drops below a committed baseline (`heal_baseline.json`) — honestly **1.0 (7/7)** over 5 covered classes (`bad_param`, `missing_index`, `oom`, `time_limit`, `tool_crash`); `recovery_rate` (4/7) is reported alongside as informational-only, never guarded. Both guards scoped to their **labeled synthetic sets only**; folding in C1/C3's unlabeled corroboration signals into one eval number, and a held-out-accuracy trend over versions, remain future work *(superseded on the second half: the trend shipped — `holdout_history.jsonl`, `heal_history.jsonl`, `--snapshot`/`--history`, and two dashboard trend cards; the C1/C3 fold-in has since shipped (Unreleased) — see the status column)*. **Both guards have now moved for the first time** (the C2 stall-watchdog slice, Unreleased): held-out accuracy **0.846 → 0.923** (12/13) — flat across all six recorded trend points, v0.22.0 → v0.48.0, with the `no_progress` case misclassified as `tool_crash` every time — and `covered_classes` **5 → 6** with outcome-match still 1.0 over 8 scenarios (recovery 5/8). Both baselines were refrozen as a deliberate act. **Read honestly:** the accuracy move is partly **self-graded** — we made reachable a class whose held-out fixture we wrote — so it evidences that a documented taxonomy gap closed, **not** that the watchdog helps a real user; and `qc_anomaly` remains the one structurally unreachable class, needing its own slice (its honest trigger is the verdict object, not log text). **That slice has now shipped (Unreleased): `qc_anomaly` is reachable and no failure class is structurally unreachable any more.** A green run — every task exit 0 — whose QC reduces to FAIL is now diagnosed as `qc_anomaly` and recorded as a `qc_verdict_flagged` step (and captured into the pending corpus, where this class could not previously land at all), lifting `covered_classes` **6 → 7** over **9** frozen scenarios with outcome-match still **1.0**, driven through the **real** `_discover_qc` by one header-only `.vcf.gz` rather than any QC-bypassing seam. **Read honestly:** `eval-guard` is **deliberately unmoved at 92.3%** — the held-out `holdout-qc-anomaly-1` case is *log-text* shaped, so closing it would need detector needles matching text Contig never emits, the `no_progress` slice's "our own wording is ordinary English" defence was unavailable, and the trade was declined (`MISS holdout-qc-anomaly-1: expected qc_anomaly, predicted tool_crash` is printed by the guard itself); **any claim that detector accuracy improved would be false**. It **recovers nothing by design** — every task exited 0, so a `-resume` retry is a 100% cache hit re-deriving an identical verdict, and no patch is proposed. The `recovery_rate` **0.625 → 0.667** move is an **artifact** of a green-by-construction scenario, not an improvement. Organic frequency is **0 of 17** recorded runs under today's bands (the single tripping bundle was authored to be bad, carries `contig_version: 0.0.1`, and its `ts_tv = 3.5` is a WARN under the current `fail_above: 3.6`) — **push, not demand-pull**, with a committed revisit trigger: zero non-authored firings across the next 20 real runs ⇒ the diagnosis path is removed and reduced to a report-only note. **The `patch_applied` slice (Unreleased) then retired that `recovery_rate` artifact.** `RepairStep` said a patch was *proposed*, never *enacted*, so a user who **rejected** a patch at the approval gate was told their run was `Repaired` (five self-heal paths record a non-null patch and return before `apply_patch` ever runs). A control-flow-derived `RepairStep.patch_applied` — set at all 11 recording sites from the `continue_` the apply helper already returned, **never** from the outcome string, since `apply_patch` runs on that helper's *first* line and the naive rule would have stamped four failure branches as applied — now backs `wasRepaired`, the reproduce env-repair steps (`retry_failed` is **applied but unsuccessful**, the case that makes the semantics legible), the text/HTML reports, and `heal-guard`'s `recovered`, which became `succeeded AND any(step.patch_applied)`. Guarded outcome-match held at **1.0** because the one corrected expectation shipped in the same commit as the redefinition; informational `recovery_rate` **0.667 → 0.556** is a correction whose sixth trend point is **not comparable** to the prior five. `eval-guard` correctly unmoved at 92.3%. Fourth but **narrowest** signature break — the key is nested, so an empty `repair_history` still verifies (tested, not asserted). **Push, not demand-pull**, and it recovers nothing new: it changes what the record *says*, not what the engine *does*. **The catalog-coverage slice (Unreleased) then widened the frozen set — and its deferral is the finding.** `heal-guard` went **9 → 16 scenarios** and `covered_classes` **7 → 11** (`missing_reference`, `reference_not_bgzf`, `container_pull_failed`, `download_failed`), guarded outcome-match **still 1.0**, informational `recovery_rate` **0.5556 → 0.5625 (9/16)**, `eval-guard` **unmoved at 92.3%** with the same single known miss and the detector corpora untouched. Seven new frozen lines — four recovering, three honest give-ups (`rejected_by_user`, `reference_recompress_unresolvable`, `gave_up`) — with the nine pre-existing lines byte-identical; the only mechanism change is `HealScenario.fasta_artifact`, a **named fixture directive** on the `qc_artifact` precedent that writes a real plain-gzip FASTA so the loop runs the **real** `_recompress_reference` rather than a mock of it. **The brief asked for all nine uncovered classes and only four shipped, deliberately:** the other five have **inert** repairs. Four are `env` patches — `disk_full`/`clean_work_dir`, `permission_denied`/`fix_permissions`, `conda_solve_failed`/`relax_or_pin_env`, `platform_unsupported`/`use_native_arch_backend` — whose operation is string-merged into `backend_options`, out of which `nfconfig.py` reads only queue/region/partition/account/qos/time, so it is consumed by **nothing**; the fifth, `container_unavailable`, is inert for a different reason kept distinct rather than flattened — its patch is `kind="retry"`, for which `apply_patch` is a *documented* no-op, so the `wait_seconds: 15` its rationale promises is silently dropped. The loop's story for all five is propose → "apply" → `patch_applied=True` → retry → `Repaired` with nothing cleaned, chmod'd, pinned, slept or re-targeted. That is **one layer below** the bug the `patch_applied` slice fixed, and freezing those five expectations would have hardened claims we already suspect are wrong into CI; a C2 follow-up is filed with **propose-vs-don't as its first question**, not "how to implement", and a gap-pinning test (`test_five_inert_patch_operations_are_still_consumed_by_nothing`) turns **red** the moment any of them is implemented or withdrawn, so the deferral reason must be revisited in that same commit. **Read honestly:** push, not demand-pull (organic frequency unmeasured); synthetic throughout, no stronger than any prior heal scenario; self-graded; it **recovers nothing new for a user** — it changes what CI *guards*, not what the engine *does*; and **`covered_classes: 11` invites over-reading** — eleven classes have a frozen synthetic scenario, which is not a claim the engine handles those failures well, and for the five excluded it demonstrably does not |

Each capability dovetails with the dashboard items above (for example C1 surfaces
as a "corroborated by" line on the verdict card, C3 extends the QC panel). It
stays inside the same guardrails restated below.

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
