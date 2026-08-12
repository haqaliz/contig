# Issue Card: fold concordance-family capture into the C6 eval flywheel

## Brief (inline, from the contig-next recommendation)

Extend the v0.51.0 C6 fold-in so the C1 concordance family is captured into
`RunRecord.verification_inputs` (pre-band metric dicts from the
`ConcordanceResult`s of all four shipped slices — germline, RNA-seq, somatic,
single-cell — plus the autorun paths), appended as pending cases like the other
families, and covered by `contig verify-guard` re-derivation.

Caveat: concordance is WARN-only and `unverified`-below-10-shared-genes by
design, so its cases rarely flip a verdict — keep the capture additive and
prove coverage with the existing mutation control rather than chasing a
headline number. Ground everything in the fold-in's shipped capture/promote
pattern; test-first, no real nf-core run or network in CI. This is the last
deferral the fold-in named, and the capture is the unblocked prerequisite for
C1's deferred FAIL-severity band calibration.

## Sources in the roadmap

- `CHANGELOG.md` v0.51.0: "the C6 fold-in ships" — `RunRecord.verification_inputs`
  capture for the multiqc, plausibility, composition, scrnaseq, methylseq/ampliseq/mag,
  and germline families; "concordance-family capture deferred" (PRD R4a).
- `docs/technical/CAPABILITY_ROADMAP.md` C6 ("Honest scope as shipped"): concordance-family
  capture remains deferred.
- `docs/technical/CAPABILITY_ROADMAP.md` C1: every slice defers FAIL severity "once
  thresholds are calibrated on real data" — capture is the prerequisite for calibration.
- The fold-in slice's shipped pattern: `docs/planning/eval-corroboration-fold-in/`
  (verify-core/, capture-promote/, verify-guard-command/).

## Decision record

- Feature slug: `eval-concordance-capture` (docs/planning/eval-concordance-capture/)
- Branch: `feat/eval-concordance-capture/aliz`
- Owner: aliz
- Worktree: `.claude/worktrees/feat-eval-concordance-capture`
