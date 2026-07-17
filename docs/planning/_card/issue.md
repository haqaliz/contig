# Card: holdout-accuracy-trend (feat)

Source: no GitHub issue — inline brief from the `contig-next` handoff (2026-07-17).
Owner: aliz. Branch: `feat/holdout-accuracy-trend/aliz`.
Capability: **C6 (Eval flywheel as a continuous loop)** — the unblocked half of its
stated-pending list.

## Brief

Build C6's unblocked pending slice: a **held-out-accuracy trend over corpus/detector
versions** for the two CI guards.

Persist each `contig eval-guard` (held-out detector accuracy, honestly 0.833 / 10:12)
and `contig heal-guard` (self-heal outcome-match rate, honestly 1.0 / 7:7) result as a
timestamped `EvalSnapshot` (or a snapshot record of that shape), keyed by
`corpus_sha` / `detector` / `contig_version`, and add a `--history` view that prints
the trajectory over versions with per-version deltas — mirroring the already-shipped
`contig eval-detector --snapshot` / `--history` and reusing `src/contig/eval_history.py`.

Test-first: a sequence of snapshots yields an ascending/descending trend, and a
regressed snapshot shows a negative delta.

## Why (from the contig-next ranking)

- C6's own explicitly-pending, **unblocked** slice. The roadmap lists two pending items
  — "folding C1/C3 signals + a held-out-accuracy trend"; the fold-in is **blocked** on an
  unbuilt labeling design, while the trend is not
  (`docs/technical/CAPABILITY_ROADMAP.md` C6 slice 2, "Still pending").
- Deepens **moat #2 — accumulated evaluation data** — by making the compounding-improvement
  claim durable and measurable rather than asserted. The frozen held-out / heal guard is a
  *more* defensible trust signal than the training-corpus `eval-detector --history` that
  already ships as a "DIFFERENTIATOR" (`FEATURES.md`).
- Expresses CLAUDE.md guardrail #3 ("gets better as base models improve"): swap in a
  stronger detector/LLM diagnoser and the frozen held-out trend visibly rises — the
  instrument that *proves* the orchestrator improves. Reuses the shipped
  `EvalSnapshot` / `default_history_path()` machinery, so low feasibility risk.

## Known caveat (settle before/at planning)

- eval-guard/heal-guard run in **CI on every build**, so writing a snapshot on every
  invocation would flood the history with identical entries. Decide **when** to persist —
  gate it behind an explicit `--snapshot` flag and/or write on `--update-baseline` (as
  `eval-detector --snapshot` does), never unconditionally.
- Decide whether the two guards share one history file with a `kind` discriminator or get
  two separate history files.
- This slice must **not** attempt the blocked C1/C3 fold-in — trend only the two
  already-labeled guard metrics.

## Guardrails

- Layer 2 only (run / self-heal / verify / reproduce). No Layer-1 workflow authoring.
- No raw-read egress; local, deterministic, no network. Test-first.
- No correctness over-claiming; the honest numbers (0.833, 1.0) are reported as-is.
