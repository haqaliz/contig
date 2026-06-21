# Contig Dashboard

A Next.js (App Router, TypeScript) dashboard for inspecting Contig runs. It reads
the run bundles (`run_record.json`) and the failure corpus directly from disk, so
it needs no separate backend. Tailwind v4 + shadcn/ui.

This is the Phase 1 "Run Inspector" from [FEATURES.md](../FEATURES.md): a
read-only surface over finished runs.

## What it shows

- **Runs** (`/runs`): every run bundle with its honest verdict (pass, warn, fail,
  unverified), pipeline and revision, task counts, and whether self-heal kicked
  in. Filter by verdict, search, and sort.
- **Run detail** (`/runs/<id>`): the verdict explained in plain language, the QC
  results (with per-sample and cross-sample drill-down), the detect to diagnose
  to patch to outcome repair timeline, and the pinned provenance.
- **Detector** (`/eval`): the failure detector scored against the labeled corpus
  (accuracy, per-class precision/recall, current misses). This shells out to
  `contig eval-detector --json`, so the detector stays in Python (the moat).

## Run it

From `dashboard/`:

```bash
npm install      # first time only
npm run dev      # http://localhost:3000
```

By default it reads `../runs` (the repo's runs directory). Point it elsewhere
with an environment variable:

```bash
CONTIG_RUNS_DIR=/path/to/runs npm run dev
```

The detector page invokes `uv run contig eval-detector --json` from the repo
root. If the CLI is not available the page degrades gracefully. Override the
command with `CONTIG_CMD` (for example `CONTIG_CMD=contig`).

## Layout

- `lib/types.ts`: TypeScript mirror of the engine's serialized models.
- `lib/runs.ts`: server-only disk access (run bundles, corpus, detector eval).
- `lib/derive.ts`: pure, client-safe helpers over a run record.
- `components/status-badge.tsx`: the accessible verdict/QC pill.
- `app/runs`, `app/runs/[id]`, `app/eval`: the three views.
