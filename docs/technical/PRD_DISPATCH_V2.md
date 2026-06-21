# PRD: Live progress, verdict explainability, one-click reproduce

Status: approved, in build. Owner: orchestrator + agent team. Target branch: master (commit and push per feature as it goes green).

This PRD specifies three features built in one pass. It pins the on-disk
contracts so the engine (Python) and dashboard (Next.js) streams can be built in
parallel against the same interface.

## Decisions (locked with the user)

1. Reproduce reads an engine-written `launch.json` sidecar, so every run (CLI or
   dashboard) is reproducible.
2. Live progress surfaces task progress, current steps, live self-heal attempts,
   and a live log tail. The log tail is collapsible via a handle so it can be
   calmed when noisy.
3. Work lands straight to master, committed and pushed per feature as it goes
   green.
4. Reproduce offers both paths: a "Reproduce exactly" one-click button and an
   "Edit and relaunch" pre-filled form.

## Non-goals

- No Layer-1 work (no NL to workflow). We consume launch inputs already captured.
- No new backend beyond local for these features. Manifest records backend so a
  future cloud run reproduces faithfully, but we test on local.
- No engine change to the verdict logic. Explainability is presentation only.

---

## Shared on-disk contracts (the integration boundary)

### A. `runs/<id>/launch.json` (engine writes; reproduce reads)

Written by `contig run` BEFORE `self_heal_run`, so it exists during the run and
on early failure. A `LaunchManifest` pydantic model serialized to JSON:

```
{
  "run_id": "run-2026-06-22T...",
  "pipeline": "nf-core/rnaseq",
  "revision": "3.26.0",
  "profiles": ["docker"],            // ["test","docker"] for a test run
  "backend": "local",
  "container_runtime": "docker",
  "input": "/abs/sheet.csv" | null,  // null => test profile run
  "genome": "GRCh38" | null,
  "fasta": "/abs/genome.fa" | null,
  "gtf": "/abs/genes.gtf" | null,
  "max_memory": "6.GB" | null,
  "max_cpus": 2 | null,
  "max_attempts": 3,
  "is_test_profile": true,           // derived: input is null
  "created_at": "2026-06-22T...Z"
}
```

Reproduce rebuilds the `contig run` argv from this with a FRESH `run_id` and the
default outdir/work_dir under the new run dir. `outdir` is NOT stored (always
re-defaulted per run).

### B. `runs/<id>/repair_progress.jsonl` (engine appends; live view reads)

One serialized `RepairStep` per line, appended the moment each self-heal attempt
resolves (the same object that later lands in `repair_history`). The final bundle
`repair_history` is unchanged. Live view reads this to show attempts as they
happen. File may be absent (no failures yet).

### C. Progress read (dashboard server; derived from existing files + B)

`getRunProgress(id)` reads `status.json`, `trace.txt`, and `repair_progress.jsonl`:

```
{
  state: "running" | "finished" | "interrupted" | "missing",
  startedAt: string | null,
  elapsedSec: number | null,           // to finishedAt if finished, else now
  tasksCompleted: number,              // trace rows with status COMPLETED
  tasksRunning: { process: string; name: string | null }[],  // status RUNNING
  submitted: number | null,            // optional: total rows in trace
  repairs: RepairStepLite[],           // parsed from repair_progress.jsonl
}
```

`trace.txt` is TSV with a header row; parse the header to find the `status` and
`name` columns (do not hard-code indices). `getRunLogTail(id, lines=200)` returns
the last N lines of `run.log` with ANSI stripped, for the collapsible panel.

### D. New / extended CLI

- `contig status <run-id> [--runs-dir] [--json]`: one-shot snapshot (state,
  elapsed, tasks completed/running, last repair attempt).
- `contig watch <run-id> [--runs-dir] [--interval 2]`: redraw the snapshot until
  state is no longer running.
- `contig rerun <run-id> [--runs-dir] [--new-run-id]`: read `launch.json`, dispatch
  an identical run (reuses the `run` path), print the new run id.
- `contig show <run-id> --explain`: print the verdict plus the deciding checks
  (value vs expected_range) and a one-line reason.

### E. `explainVerdict(record)` (dashboard `lib/derive.ts`, client-safe)

Mirrors `models.py` exactly; never re-derives trust, only explains the recorded
verdict:

```
explainVerdict(record) -> {
  verdict: "pass" | "warn" | "fail" | "unverified",
  reason: string,
  decidingChecks: QCResult[],   // checks whose status drove the verdict
}
```

- any failed task event -> `fail`, reason "Run did not complete: N task(s) failed".
- else no qc_results -> `unverified`, reason "No QC check covered this run".
- else overall = fail > warn > pass; decidingChecks = checks whose status == overall;
  reason e.g. "WARN: 3 of 174 checks flagged (lowest: salmon_mapping_rate 58.1 vs >= 60.0)".

### F. Reproduce (dashboard)

- `getLaunchManifest(id)`, `dispatchReproduce(id)` in `lib/runs.ts` (reads manifest,
  validates inputs as the existing dispatch does, new server-generated run id).
- Run detail: "Reproduce exactly" -> dispatch -> redirect to
  `/runs/compare?a=<orig>&b=<new>`. "Edit and relaunch" -> `/runs/new?from=<id>`.
- Launch form reads `?from=<id>`, loads the manifest, pre-fills the fields.

---

## Feature 1: Live run progress

Engine: write `repair_progress.jsonl` incrementally in the self-heal loop (TDD).
CLI: `status`, `watch`. Dashboard: `getRunProgress` + `getRunLogTail`, a richer
`RunningView` that polls and renders a progress summary + currently-running steps
+ live self-heal attempts + a collapsible log tail (handle to open/close so the
noisy log can be calmed). The in-progress view must remain honest: show completed
count and running steps; do not fabricate a percentage when the total is unknown.

## Feature 2: Why this verdict

No engine model change. CLI: `show --explain`. Dashboard: `explainVerdict` in
`derive.ts`; the verdict card gains a "Decided by" section listing the deciding
checks with value vs expected_range; the QC tab sorts fail/warn checks to the top.

## Feature 3: One-click reproduce

Engine: `LaunchManifest` model + write `launch.json` in `contig run`; `rerun`
command. Dashboard: read manifest, "Reproduce exactly" + "Edit and relaunch",
launch-form prefill from `?from=`.

---

## Verification

- Engine: strict TDD (RED before GREEN). Full `uv run pytest` green (currently 287).
- Dashboard: `npx tsc --noEmit` + `npm run lint` clean; Playwright e2e green, with
  new specs for live progress (fixture run dir), explain, and reproduce.
- Cross-layer: the dashboard codes against the pinned schemas above; final
  integration confirms a real run writes `launch.json` and (on failure)
  `repair_progress.jsonl` matching the schemas.

## Style / security constraints (carried from the project)

- No em dash, en dash, or hyphen-as-pause anywhere (code, comments, docs, commits).
  Use commas, colons, parentheses. Plain hyphens only in compound words.
- Any user-controlled value reaching the CLI is validated (charset, no leading
  dash) and passed as `--opt=value` with a `--` terminator before positionals.
- Reproduce re-validates input paths at dispatch (do not trust the manifest blindly).
