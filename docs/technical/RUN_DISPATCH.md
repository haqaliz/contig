# Run Dispatch: launching runs from the dashboard (design proposal)

Status: proposal, awaiting approval. Nothing here is built yet.

This is the keystone of P2 ("make the dashboard interactive"): a user goes from
data to a verified result inside the UI, instead of only inspecting runs that
were launched from the CLI. It is deferred for a design decision because it
executes real pipelines (Nextflow plus Docker) on the user's machine, which has
security and operational implications the rest of the dashboard does not.

## Goal

From the dashboard: pick or describe an analysis, review the proposed plan,
approve it, and launch. The run then appears in the run list as "running" and
shows its verdict when it finishes. No separate Python server.

## The constraint it must respect

The dashboard has no backend service: it reads run bundles and corpus JSON from
disk, and shells out to the `contig` CLI only when it needs the engine (the
detector eval already does this). Run dispatch must fit that same model, not
introduce a long-lived job server.

## Architecture

A Next.js route handler (server side) spawns the existing CLI as a detached
child process and returns immediately. The child writes to `runs/<id>/` exactly
as a CLI run does. The dashboard observes progress by reading that directory.

```
Browser (approve + launch)
   |  POST /api/runs   (validated form: pipeline, reference, sheet path, caps)
   v
Next route handler (server)
   |  spawn detached:  contig run --run-id <id> --input ... --runs-dir runs ...
   |  (argv array, never a shell string; writes runs/<id>/status.json)
   v
contig run  (the existing self-heal + verify engine, unchanged)
   |  writes trace.txt, run.log, work/, then run_record.json (verdict)
   v
Dashboard reads runs/<id>/ to show state, then the verdict bundle
```

The engine does not need to know it was launched from the web. We reuse
`contig run` as is.

## The launch flow (UI)

1. New run form: pipeline (from the curated registry), reference (iGenomes key
   or fasta and gtf paths), sample sheet path on disk, optional resource caps and
   backend.
2. Plan and approve: shell out to `contig plan` to show the proposed pipeline,
   params, and warnings. The user approves before anything runs (this is the
   existing approve-before-run promise, made interactive).
3. Launch: POST to the route handler, which validates, spawns the run detached,
   writes a status marker, and redirects to `/runs/<id>`.
4. The run detail page shows the "running" state and polls (a simple refresh
   interval). When `run_record.json` appears, it shows the verdict.

## Run status without a live stream (v1)

Today `run_record.json` only appears at the end (on success or on a captured
failure), so a running or crashed run is currently invisible to the list. v1
adds a small, first-class status marker so any run is observable:

- The engine writes `runs/<id>/status.json` at the start of a run (`running`,
  with `started_at`), and updates it at the end (`done` or `failed`, with
  `finished_at`). This is a small, testable engine addition, and it makes runs
  observable no matter who launched them (CLI or web).
- The dashboard derives state per run: if `run_record.json` exists, use its
  verdict; else if `status.json` says `running`, show "running"; else if the
  marker is stale (process gone, no record), show "interrupted".

Per-task live progress (which step is running right now) is NOT in v1. It needs
the engine status-stream work flagged in FEATURES.md and is a separate milestone.

## Security and safety (the reason this needs a decision)

A dashboard that triggers pipeline execution is a different risk class from a
read-only viewer. The mitigations:

- **No shell strings.** Spawn with an argv array (execFile/spawn with args), so
  there is no command injection surface. User values are separate arguments.
- **Validated inputs.** Run id is generated and pattern-checked. The pipeline is
  restricted to the curated registry. Reference and sheet paths must exist and
  resolve inside an allowed root (no traversal). Resource caps are format-checked.
  The sheet itself is pre-flight validated by the engine before launch (already
  built).
- **Localhost only, no auth, for v1.** This is a local single-user tool. The
  dashboard must bind to localhost and must not be exposed to a network. If we
  ever host it, dispatch needs authentication and a permission model first. This
  is documented as a hard boundary.
- **Concurrency cap.** Runs are heavy (Docker, CPU, RAM). v1 limits how many run
  at once (proposal: one at a time, configurable), and refuses a run id whose
  directory already exists.

## Engine work needed

Small and TDD-able:

1. `status.json` lifecycle in `run_pipeline` (write `running` at start, `done` or
   `failed` at end). The cleanest place for run observability, and it serves the
   CLI too.
2. Nothing else for v1a. v1b reuses the existing `plan`, `run`, sample-sheet
   validation, and reference resolution unchanged.

## Phasing

- **v1a (plumbing, safest):** a "Run the test profile" action that dispatches
  `contig run --run-id <id>` with no inputs. Proves dispatch, the status marker,
  and the running-to-verdict flow end to end with zero input risk. Small and
  demonstrable.
- **v1b (real data):** the launch form (sheet path, reference, pipeline, caps)
  with plan-and-approve and the validation above.
- **v2 (live progress):** per-task progress and a self-heal activity feed, which
  require the engine status-stream work. Separate milestone.

## Decisions needed from you

1. **Input model for the first cut:** start with v1a (test-profile button) to land
   the plumbing safely, then v1b? Or go straight to v1b (the real-data form)?
2. **Sample sheet:** point at a path already on disk (simplest, matches the
   local-compute model), or support uploading the CSV in the browser?
3. **Concurrency:** one run at a time for v1, or allow a small number?
4. **Security boundary:** confirm localhost-only and no auth is acceptable for now
   (it is a local tool), with network exposure explicitly out of scope until we
   add auth.
5. **Status marker home:** confirm the engine owns `status.json` (recommended), so
   runs are observable whether launched from the CLI or the web.
