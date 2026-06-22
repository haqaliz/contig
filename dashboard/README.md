<img src="public/logo.svg" alt="Contig" width="80" />

# Contig Dashboard

A Next.js (App Router, TypeScript) dashboard for Contig. It reads run bundles
(`run_record.json`), live run state, the failure corpus, and the eval history
directly from disk, and shells out to the `contig` CLI for actions (launch,
cancel, resume, approve, verify), so it needs no separate backend. Tailwind v4 +
shadcn/ui (on Base UI).

It started as the read-only "Run Inspector" and now covers the full Layer-2 loop:
launch a run, watch it live, steer the self-heal, verify and reproduce the result,
compare runs, curate the failure corpus, and track the detector over time.

> Localhost-only, no auth. It runs the CLI on your machine and can launch and
> cancel real pipelines, so do not expose it to a network.

## What it does

- **Runs** (`/runs`): every run bundle with its honest verdict (pass, warn, fail,
  unverified), pipeline and revision, task counts, and whether self-heal kicked
  in. Filter, search, and sort. Header actions: **Run test profile**, **New run**,
  and **Compare runs**. A live "In progress" section lists runs that are still
  going.
- **New run** (`/runs/new`): a launch form (goal, sample-sheet path, an iGenomes
  key or a fasta + gtf pair, optional resource caps). Preview the plan, then
  launch. `?from=<id>` pre-fills it from a past run's launch manifest.
- **Run detail** (`/runs/<id>`): the verdict explained in plain language with the
  deciding QC checks, an output-integrity badge (verified, drift detected, or not
  captured) with a **Verify** action, the QC results (per-sample and cross-sample
  drill-down), the detect to diagnose to patch to outcome repair timeline, the
  pinned provenance, and **Reproduce exactly** / **Edit and relaunch**.
- **Live run view**: while a run is in flight the page polls a snapshot (elapsed,
  tasks completed, currently running steps, live self-heal attempts) with a
  collapsible log tail and a **Cancel** button. If the self-heal loop proposes a
  risky patch the run pauses and the page shows **Approve** / **Reject** (a
  destructive patch needs a second confirm). A cancelled or interrupted run offers
  **Resume** (re-runs from the cached tasks).
- **Compare** (`/runs/compare`): pick two runs and diff verdict, pipeline, params,
  checksums, container digests, task counts, and QC, with a reproduced or not
  reproduced summary.
- **Pending** (`/pending`): review auto-captured failure cases and confirm or
  correct their label, promoting them into the golden corpus (moat #2).
- **Detector** (`/eval`): the failure detector scored against the labeled corpus
  (accuracy, per-class precision/recall, current misses), a **detector selector**
  (rules, rules-strict) that scores any registered detector, and an
  accuracy-over-time trend with per-class deltas. The detector stays in Python
  (the moat); the page shells out to `contig eval-detector --json`.
- **Notifications**: a header activity bell reads `notifications.jsonl` and shows
  recent run events; a run waiting for your approval links straight to it.

## Run it

From `dashboard/`:

```bash
npm install      # first time only
npm run dev      # http://localhost:3000
```

By default it reads `../runs` and runs `uv run contig` from the repo root. If the
CLI is unavailable, pages that need it degrade gracefully. Environment overrides:

| Variable | Default | What it controls |
|---|---|---|
| `CONTIG_RUNS_DIR` | `../runs` | Where run bundles, status, and `notifications.jsonl` are read |
| `CONTIG_CMD` | `uv run contig` | The CLI used for read-only calls (e.g. eval-detector) |
| `CONTIG_DISPATCH_CMD` | `uv run contig` | The CLI used to launch and control runs (dispatch, cancel, resume, approve, verify) |
| `CONTIG_EVAL_HISTORY` | shipped path | The eval-history file the trend reads |

## Testing

- `npx tsc --noEmit` and `npm run lint` for types and lint.
- `npx playwright test` for the end-to-end suite. It runs against synthetic run
  fixtures in `e2e/fixtures/`, provisioned into the runs directory only for the
  duration of the suite (global setup and teardown) so they never clutter a real
  dashboard. `PW_PORT` runs the suite on an isolated port when another app holds
  3000.

## Layout

- `lib/types.ts`: TypeScript mirror of the engine's serialized models.
- `lib/runs.ts`: server-only disk access and CLI shell-outs (bundles, status,
  progress, corpus, eval, notifications, dispatch, cancel, resume, approve, verify).
- `lib/derive.ts`: pure, client-safe helpers over a run record (verdict
  explanation, task counts, QC sorting).
- `components/`: the verdict card, QC panels, repair timeline, live run view,
  approval gate, notifications bell, output-integrity card, and the shared UI.
- `app/runs`, `app/runs/new`, `app/runs/[id]`, `app/runs/compare`, `app/pending`,
  `app/eval`: the views. `app/api/runs/[id]/*`: the action routes.
