# Issue Card: fold the reproduce track into the C6 eval flywheel

## Brief (inline, from the contig-next recommendation)

Fold the reproduce track into the C6 eval flywheel: every C8 slice defers "the
C6 eval fold-in" (CAPABILITY_ROADMAP.md C8), and C8's own framing promises "a
whole new, publicly-sourced stream of failure-and-fix data feeding C6". Build
`contig reproduce-guard` mirroring the shipped heal-guard/verify-guard pattern —
replay frozen reproduction scenarios through the real `run_reproduction` loop
(claims, executors, locators, env-resurrection seams never stubbed) and guard
per-claim verdict-match rate against a committed baseline, plus a capture
channel from ReproduceRecord outcomes into the corpus (pending-corpus sidecar
precedent; the signed record is untouched).

Caveats to honor from the docs: the guarded number starts synthetic/self-graded
like verify-guard's v0.51.0 disclosure, no real repo or network in CI (injected
seams only, real-repo smoke test as a manual gate), and it is push, not
demand-pull — record honest scope in the roadmap and CHANGELOG per house style.

## Sources in the roadmap

- `docs/technical/CAPABILITY_ROADMAP.md` C8: "Eval data captured: every
  reproduction attempt (the environment-repair chain, the per-claim diff
  outcome) is a labeled corpus case — a whole new, publicly-sourced stream of
  failure-and-fix data feeding C6." And the C6 eval fold-in is named in the
  deferred list of nearly every C8 slice (slices 1, 1.5, 3, 4, 5, 6, 8, and
  extract-claims).
- `docs/technical/CAPABILITY_ROADMAP.md` C6: the fold-in framing — "Feed
  concordance outcomes (C1), new repair outcomes (C2), and plausibility
  outcomes (C3) into the eval history alongside the detector scores" — and the
  shipped slice-1/slice-2 precedent (`eval-guard`, `heal-guard`) plus the
  v0.51.0 `verify-guard` fold-in.
- `CHANGELOG.md` v0.51.0: verify-guard shipped "as the labeling design plus a
  new sibling guard" — the design precedent for labeling a verification signal
  that has no stored ground truth.
- `docs/technical/CAPABILITY_ROADMAP.md` C6 (`eval-concordance-capture`, v0.53.0):
  the pending-corpus sidecar capture precedent that never touches the signed
  record — the pattern the reproduce capture must follow.
- The shipped guard patterns: `docs/planning/eval-holdout-guard/`,
  `docs/planning/self-heal-eval-guard/`, `docs/planning/eval-corroboration-fold-in/`.

## Decision record

- Feature slug: `reproduce-eval-fold-in` (docs/planning/reproduce-eval-fold-in/)
- Branch: `feat/reproduce-eval-fold-in/aliz`
- Owner: aliz
- Worktree: `.claude/worktrees/feat-reproduce-eval-fold-in`
- Task source: inline brief (no GitHub issue filed for this slug)
