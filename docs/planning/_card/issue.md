# Card: self-heal-eval-guard (feat)

Type: feat · id/slug: `self-heal-eval-guard` · owner: aliz
Branch: `feat/self-heal-eval-guard/aliz`
Source: no GitHub issue — inline brief from `/contig-next` handoff (2026-07-07).
Capability: **C6 (eval flywheel), slice 2 — the labelable half.**

## Brief

Build capability **C6's next slice** (eval flywheel): a frozen held-out benchmark
that scores and regression-guards the **whole self-heal loop's recovery rate**
(detect → diagnose → patch → retry), not just the detector's classification
accuracy that `contig eval-guard` already covers (shipped v0.17.0).

The moat's single biggest measurement gap: `contig eval-guard` guards whether
Contig *diagnoses* right (detector classification accuracy on a held-out
`FailureCase` corpus). **Nothing measures whether the loop actually *recovers*.**
Yet recovery rate *is* the Phase 1→2 gate — "≥70% unattended completion on the
core pipeline" (`docs/ROADMAP.md:109`) — and the Phase 3 flywheel target
"measurable improvement in self-heal" (`docs/ROADMAP.md:161`). We guard the
diagnosis but not the cure.

This is the **labelable half** of the C6-slice-2 deferral
(`CAPABILITY_ROADMAP.md:497-501`, "repair-loop (whole self-heal) accuracy into one
number"). The C1/C3 half of that fold is blocked on a labeling design (no
ground-truth labels); self-heal outcomes are cleanly labelable (recovered vs
gave-up), so this carves off the unblocked sub-slice.

## What to build

- A frozen held-out set of injected-failure scenarios driven through the
  **injectable seams** on `self_heal_run(..., executor=…, index_builder=…)`
  (`src/contig/self_heal.py:793-803`), reusing the scripted fail-then-succeed
  `executor(cmd, trace_path)` pattern already in `tests/test_self_heal.py`.
- Extend the shipped `holdout.py` / `EvalSnapshot` / `compare_to_baseline`
  plumbing from detector scoring to **loop scoring**.
- A `contig heal-guard` command (mirroring `contig eval-guard`) that **fails the
  build** when whole-loop recovery drops below a committed baseline, with
  `--update-baseline` to refreeze deliberately. Wire into CI after the pytest step,
  as `eval-guard` is.

## Moat / guardrail fit

- **Layer 2** (self-heal + verify + the compounding eval flywheel): dead center.
- Deepens **moat #2** (the compounding eval dataset) *and* measures **moat #1**
  (the self-heal loop) for the first time.
- **Gets better as base models improve**: a better diagnoser/patcher raises the
  number and a regression drops it — provably.
- Follows a **shipped pattern** (rule: follow-on slices count): extends
  `eval-guard`/`holdout.py`.

## Known caveats (design around these; do not paper over)

1. **Synthetic scenarios, not the field distribution.** Held-out heal scenarios
   are synthetic injected failures through the executor seam — same honesty class
   as the detector held-out set's `source="holdout:synthetic"`. The number measures
   recovery against *reproducible synthetic* failures, **not** a real-world recovery
   rate. Label it as such everywhere; never present it as a field metric.
2. **Coverage bounded to injectable failure kinds.** Only failure classes whose
   seams are injectable in CI (`executor`, `index_builder`) can be exercised; kinds
   needing a real tool build can only be driven at the seam boundary. The first
   slice must **enumerate the covered `FailureClass`es** and document/`log` the ones
   it can't yet. The committed baseline will be an honest *partial-coverage* number
   — exactly as `eval-guard` shipped at 0.833 with two structurally-unreachable
   classes.

## Grounding (verified against code, 2026-07-07)

- `contig eval-guard` exists at `src/contig/cli.py:1579`; scores the **detector**
  (`evaluate_detector` in `corpus.py`), not the loop.
- `holdout.py`: `default_holdout_path`, `default_baseline_path`, `save_baseline`,
  `load_baseline`, `compare_to_baseline`, `EvalSnapshot` — all detector-scoped today.
- `self_heal_run(..., executor: Executor = default_executor,
  index_builder: IndexBuilder = default_index_builder)` — fully injectable seams.
- `tests/test_self_heal.py` — ~15 scripted `executor(cmd, trace_path)` fail-then-
  succeed scenarios + a `_heal(tmp_path, executor, **over)` helper.
- Baseline suite (this worktree, origin/master): **1176 passed, 1 skipped**.

## Non-goals (this slice)

- Folding the **unlabeled** C1 concordance / C3 plausibility corroboration signals
  into the same guard (deferred — needs a labeling design).
- A real-run / field recovery-rate metric.
- Any Layer-1 (NL → workflow) surface.
