# Issue Card: reproduce capture/promote channel (C6 eval fold-in, capture half)

## Brief (inline, from the contig-next recommendation)

Close the C6 capture gap the `reproduce-eval-fold-in` slice left open: capture
reproduce outcomes from `ReproduceRecord` into a pending corpus (pending
`ReproduceCase` sidecar, per CHANGELOG Unreleased "the capture-promote aspect
remains the pending follow-on slice"), plus `contig reproduce-case-promote`
mirroring the shipped `verify-case-promote` pattern. Never touch the signed
record; capture rides the pending-sidecar precedent from
`eval-concordance-capture` (v0.53.0). Wire a `reproduce-guard`-style
mutation-control pin so capture writes cases and never moves the 13/14
baseline. Caveat: the corpus starts empty and the slice is push, not
demand-pull — record that honest scope in the roadmap and CHANGELOG per house
style, and decide what a `ReproduceCase` labels (per-claim statuses, repair
chain, locator family) by studying `src/contig/verify_corpus.py`'s
`VerificationCase`.

## Sources in the roadmap

- `CHANGELOG.md` [Unreleased] (reproduce-eval-fold-in): "The **capture channel
  has NOT shipped**: capture of reproduce outcomes (pending `ReproduceCase` +
  promote, the capture-promote aspect) remains the **pending follow-on slice**,
  and the corpus only becomes non-tautological as real runs feed it through
  that channel."
- `docs/technical/CAPABILITY_ROADMAP.md` C8: "Still deferred: the
  capture/promote channel — capture of reproduce outcomes (pending
  `ReproduceCase` corpus + `reproduce-case-promote`) is the follow-on slice
  (aspect capture-promote); the corpus only becomes non-tautological as real
  runs feed it through that channel."
- `docs/technical/CAPABILITY_ROADMAP.md` C6: "Eval data captured: every
  reproduction attempt (the environment-repair chain, the per-claim diff
  outcome) is a labeled corpus case — a whole new, publicly-sourced stream of
  failure-and-fix data feeding C6."
- `docs/technical/CAPABILITY_ROADMAP.md` C6 (`eval-concordance-capture`,
  v0.53.0): the pending-corpus sidecar capture precedent that never touches the
  signed record — the pattern the reproduce capture must follow.
- `docs/planning/eval-corroboration-fold-in/`: `verify-case-promote` and the
  `VerificationCase`/`verify_corpus_holdout.jsonl` labeling design precedent.

## Task source

Inline brief (no GitHub issue filed for this slug). Owner: aliz.
