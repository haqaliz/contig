# PRD: notifications, AWS-ready, output-integrity, pluggable detector, scRNA-seq

Status: approved, in build. Target branch: master (commit and push per feature as it goes green).

Five roadmap items built in one pass by a 3-agent team. Ownership is split by file
so the streams never edit the same file: Engine-Core owns the CLI chokepoint and
cli/models, Engine-Detector owns the detector seam and the assay (no cli.py,
no models.py, no self_heal.py), Dashboard owns the UI. Cross-module calls are
pinned below so the streams build in parallel.

## Decisions (locked with the user)

1. Notifications: in-app feed + webhook + email (SMTP via env; a no-op when unset).
2. AWS Batch: submission-ready (hardened config + a preflight that refuses a
   misconfigured launch) + offline tests + a runbook. No live cloud spend here.
3. Pluggable detector: a swappable detector interface, eval-detector scores ANY
   registered detector, plus a second non-LLM detector. The LLM provider plugs in
   later behind the same interface.
4. Third assay: scRNA-seq (nf-core/scrnaseq) with a per-cell QC rule pack.

## File ownership (no two streams touch the same file)

- Engine-Core: cli.py, models.py, self_heal.py, bundle.py, nfconfig.py, runner.py,
  NEW notify.py, NEW verify.py, docs/technical/AWS_BATCH_RUNBOOK.md, + their tests.
- Engine-Detector: detect.py (+ NEW detector registry), registry.py, datashape.py,
  src/contig/verification/* (scRNA rule pack + rule_pack_for wiring), corpus.py,
  + their tests. Does NOT touch cli.py, models.py, self_heal.py.
- Dashboard: dashboard/** + e2e fixtures.
- Orchestrator (integration): wires `contig eval-detector --detector` in cli.py
  (one small flag calling Engine-Detector's pinned API), runs full verification,
  commits.

---

## Pinned contracts

### A. Notifications (Engine-Core writes; Dashboard reads)

`src/contig/notify.py`: `emit_event(runs_dir, run_id, kind, message, *, webhook=None)`
appends one JSON line to `<runs_dir>/notifications.jsonl`:
`{ts, run_id, kind, message}` where kind is one of `finished|failed|cancelled|awaiting_approval`.
If `webhook` is set, POST that JSON to the URL (best-effort, never crashes the run).
Email: if `CONTIG_SMTP_HOST/PORT/USER/PASSWORD/FROM/TO` env are set, send the same
payload by SMTP; otherwise no-op. self_heal emits on transitions: `awaiting_approval`
when it pauses, `finished`/`failed` at finalize. lifecycle cancel emits `cancelled`.
`contig run --notify <url>` passes the webhook through. Best-effort: a failing
webhook/email is logged, never fails the run.

Dashboard: read `<runsDir>/notifications.jsonl` (newest first) into a header bell /
activity panel; an `awaiting_approval` event links to the run.

### B. Output integrity (Engine-Core)

`bundle.compute_output_checksums(results_dir) -> dict[str,str]` maps each output
file's path relative to results_dir to its sha256 (skips if results_dir absent).
self_heal `_finalize` populates `record.output_checksums` before write_bundle.
`contig verify <id> [--runs-dir] [--json]` re-hashes the files on disk against the
recorded checksums and reports `{ok: bool, changed: [...], missing: [...]}`; exit
non-zero on any drift. Empty recorded checksums => report "nothing to verify".

Dashboard: POST `/api/runs/[id]/verify` shells `contig verify <id> --json`; show an
"outputs verified / drift detected / not captured" badge on the run detail page.

### C. Pluggable detector (Engine-Detector exposes; Orchestrator wires CLI)

In detect.py: a `Detector` type = a callable `(events: list[TaskEvent], log_text:
str) -> Diagnosis`. A registry `DETECTORS: dict[str, Detector]` with at least
`"rules"` (the current diagnose_failure) and a second variant `"rules-strict"`
(e.g. higher-precision: prefers `unknown`/`tool_crash` when evidence is weak).
`get_detector(name) -> Detector` (KeyError -> a clear error). diagnose_failure stays
the default and self_heal keeps calling it unchanged.
`corpus.evaluate_detector(cases, detector: Detector | None = None) -> DetectorEvalReport`
(default = rules). Do NOT change DetectorEvalReport's schema.
Orchestrator adds `contig eval-detector --detector <name>` (default "rules") that
resolves get_detector and passes it to evaluate_detector.

Dashboard: a detector selector on /eval (`?detector=`) calling `contig eval-detector
--detector <name> --json`; the existing accuracy/per-class view renders the result.

### D. scRNA-seq assay (Engine-Detector)

registry.py: add `PipelineEntry(assay="scrnaseq", pipeline="nf-core/scrnaseq",
revision=<pin a real released tag>, description=...)` and scRNA keywords in the
match_assay map (single cell, single-cell, scrna, scrna-seq, 10x). datashape.py:
scRNA does not expect bulk replicates (exclude scrnaseq from _REPLICATE_ASSAYS).
src/contig/verification: add `SCRNASEQ_RULE_PACK` and wire `rule_pack_for("scrnaseq")`
to return it. Per-cell QC checks from the pipeline's MultiQC/STARsolo metrics, e.g.
estimated cells >= a floor, median genes per cell >= a floor, fraction reads in
cells >= a floor, mito fraction <= a ceiling. Mirror the existing RNA-seq/variant
rule-pack style (data-driven checks via the existing evaluate()). No cli.py change:
`assay_for_pipeline("nf-core/scrnaseq")` returns "scrnaseq" from the registry, and
the CLI already routes assay -> rule_pack_for.

### E. AWS Batch readiness (Engine-Core)

nfconfig.py: keep generate_nextflow_config; add `preflight_aws_batch(target) ->
list[str]` returning human-readable problems (queue missing, region missing,
work_dir not an s3:// URI, AWS credential env absent). `contig run` with
`--backend aws_batch` runs the preflight and refuses with the listed problems
before launching. Offline tests cover config text + each preflight rejection.
docs/technical/AWS_BATCH_RUNBOOK.md: a step-by-step guide (AWS creds, an S3 work
dir, a Batch queue, the exact `contig run --backend aws_batch ...` command, and
what a from-scratch PASS looks like) so the user can run the live test themselves.

---

## Verification

- Engine: strict TDD (RED before GREEN). Full `uv run pytest` green (currently 363).
  No test may hit the network (webhook/email/LLM) or real AWS: inject a fake
  sender/poster and use env-gated no-ops.
- Dashboard: `npx tsc --noEmit` + `npm run lint` clean; Playwright green with new
  fixtures (a run with notifications.jsonl, a run with output_checksums for verify,
  an eval detector selector, a scrnaseq run bundle). New synthetic fixtures go in
  dashboard/e2e/fixtures and are provisioned by the existing global setup, NOT into
  the real runs directory.
- Cross-layer: confirm the engine sidecar shapes (notifications.jsonl, verify JSON,
  eval-detector --detector JSON) match what the dashboard reads.

## Style / security constraints (carried)

- No em dash, en dash, or hyphen-as-pause anywhere (code, comments, docs, commits).
- Any user value reaching the CLI is validated (charset, no leading dash) and
  passed as `--opt=value` with a `--` terminator before positionals.
- Webhook/email/verify are best-effort and never crash a run; secrets come only
  from env, never logged.
