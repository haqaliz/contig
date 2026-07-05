# Card: feat/eval-holdout-guard

- **Type:** feat
- **Id/slug:** eval-holdout-guard
- **Owner:** aliz
- **Branch:** feat/eval-holdout-guard/aliz
- **Source:** inline brief (no GitHub issue; produced by the `contig-next` handoff)

## Brief

Build the first concrete slice of **C6 — eval flywheel as a continuous loop**
(`docs/technical/CAPABILITY_ROADMAP.md` §C6, lines 390-414). C6 is the one pending
engine capability whose dependencies (C1–C5) have now all shipped through v0.16.0, and
it is not started: there is no held-out corpus split and no regression-guard command in
`src/` today (grep confirms "held-out" appears only as a to-build in `CAPABILITY_ROADMAP.md:404-407`
and `ROADMAP.md:168`).

**The slice:**

- Freeze a **held-out split** of the labeled detector corpus.
- Add a single command that scores the current detector against that held-out split.
- Add a **regression guard**: a corpus or detector change that lowers held-out accuracy is
  flagged before it ships.

**Reuse, don't rebuild.** The pieces C6 consumes are already shipped: `EvalSnapshot`
(`src/contig/models.py:397`), the committed `eval_history.jsonl` +
`src/contig/eval_history.py`, `contig eval-detector --snapshot/--history`
(`src/contig/cli.py:1485`), and the `benchmark`/`coverage`/`clusters` commands. This slice
wraps that machinery with a held-out split and a guard — it does not reinvent the detector
eval.

**Test-first acceptance** (the roadmap's own, `CAPABILITY_ROADMAP.md:409-411`):
a frozen held-out set; a known-good detector scores above a threshold; a deliberately worse
detector is flagged as a regression.

## Why this is the moat (grounding)

- It is **moat #2 made real** — `CLAUDE.md`: the moat is "execution/verification/reproducibility
  infrastructure **+ accumulated workflow-evaluation data**." C6 turns the accumulated eval
  data into a measured, regression-guarded loop so every other shipped verdict compounds
  instead of silently drifting.
- It **gets better as base models improve and can't be made redundant by them** (`CLAUDE.md`
  constraint #3): the model-swap harness already exists (`FEATURES.md:225`); a held-out
  benchmark is what lets a better diagnoser be *proven* better rather than asserted.
- It is **Layer 2** (verification/eval infrastructure), inside the founder's edge (pure
  engineering, no wet-lab/clinical), and its only prior blocker ("consumes C1–C5") is now
  satisfied.

## Known caveat / the one real design decision (from the contig-next dig)

The roadmap's aspirational framing folds "C1–C5 outcomes" into one accuracy number, but
**concordance (C1) and plausibility (C3) signals are WARN-capped corroboration WITHOUT
ground-truth labels** — they cannot be scored as classification accuracy the way the labeled
failure-class detector corpus can. So the honest first slice is:

> **a frozen held-out split of the labeled failure-class corpus + a detector-accuracy
> regression guard** — NOT a grand unified "verification accuracy" folding in unlabeled
> signals.

The one real design decision is the **split boundary**: where the held-out split physically
lives so it can never leak into the training/eval corpus that `eval-detector` already scores
over the whole of. Folding in the unlabeled C1/C3 signals is explicitly a **later slice** that
needs its own labeling design; flag it, don't build it here.

## Strategic guardrails (must hold)

- No Layer-1 workflow authoring as a product surface.
- No raw-read egress; deterministic, local, no network in tests.
- Nothing needing wet-lab/clinical credentials or proprietary datasets.
- No correctness over-claiming; UNVERIFIED is never rendered as PASS.
- Test-first: every unit lands with its failing test written first.
