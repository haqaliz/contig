# Aspect spec: holdout-guard

Parent PRD: `docs/planning/eval-holdout-guard/prd.md`. Single aspect (the whole slice).

## Problem slice & user outcome

Give the maintainer a command that scores the detector against a **frozen, non-leaking
held-out set** and **exits non-zero when accuracy drops below a committed baseline** — so a
corpus edit or detector change that regresses diagnosis is caught before it ships.

## In scope

- A frozen `src/contig/data/detector_corpus_holdout.jsonl` of newly authored synthetic cases
  (`source` prefix `holdout:`), disjoint from the training corpus.
- A held-out loader (`default_holdout_path`) reusing `load_corpus`.
- A committed baseline artifact (`src/contig/data/holdout_baseline.json`, an `EvalSnapshot`).
- A `contig eval-guard` command: score held-out via `evaluate_detector` + `get_detector`,
  compare to baseline (fail-on-drop, exit≠0), `--update-baseline` to (re)freeze.
- Loud non-failing warnings on held-out-sha ≠ baseline-sha and on detector ≠ baseline-detector.
- A non-failing "accuracy improved — consider `--update-baseline`" nudge.

## Out of scope

- Folding in unlabeled C1/C3 signals; repair-loop accuracy; auto-growing the held-out set;
  per-detector baselines (S1, may be a fast follow); any Layer-1 surface.

## Acceptance criteria (testable)

- **AC1 (leakage):** held-out `case_id`s ∩ training `case_id`s = ∅; `eval-detector`/`coverage`/
  `clusters` still default to the training corpus (held-out file is never their default).
- **AC2 (score):** `eval-guard` reports an accuracy over exactly the held-out cases, backed by
  `evaluate_detector`.
- **AC3 (guard, roadmap acceptance verbatim):** known-good `rules` detector ≥ baseline → exit 0;
  a deliberately worse detector < baseline → exit 1, output says REGRESSION.
- **AC4 (freeze):** `--update-baseline` writes an `EvalSnapshot`-shaped baseline pinning the
  held-out sha + detector; a subsequent guard run against it passes.
- **AC5 (honesty):** no baseline present (and not updating) → exit 1 with a clear message;
  held-out-sha mismatch and detector mismatch → loud stderr warning but not a failure by itself;
  improvement → stdout nudge, exit 0.
- **AC6:** full suite green; deterministic; no network; `llm` never the guard default.

## Dependencies & sequencing

Phase A (data+loader) → Phase B (baseline+comparator, pure) → Phase C (CLI) → Phase D (freeze
baseline + docs) → Phase E (optional: wire into CI). B's pure comparator unit tests are
independent of A.

## Risks specific to this aspect

- Authoring held-out cases the current `rules` detector classifies as intended (iterate against
  `evaluate_detector`). Tests must assert **relations** (good ≥ baseline; worse < baseline), not a
  hardcoded baseline number, so the committed baseline can be derived empirically.
- The held-out set freezes *currently-correct* behavior (a regression guard), not generalization
  to unseen-hard cases — an adversarial/harder benchmark is future work; state it, don't overclaim.
