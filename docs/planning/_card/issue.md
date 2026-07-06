# Card: single-cell RNA-seq biological-plausibility verification

- **Type:** feat
- **Slug:** single-cell-plausibility
- **Owner:** aliz
- **Branch:** feat/single-cell-plausibility/aliz
- **Source:** inline brief (no GitHub issue) — selected by `contig-next` on 2026-07-07
- **Capability:** C3 (biological-plausibility verification), single-cell follow-on slice

## Brief

Extend C3 biological-plausibility verification to the already-shipped single-cell
RNA-seq (`scrnaseq`) assay, which today gets structural/QC checks but **no biological
verdict** (confirmed: `runner.py:_discover_qc` wires plausibility only for
`variant_calling`, `somatic_variant_calling`, and `rnaseq` — lines 67–120).

Add a `SCRNASEQ_PLAUSIBILITY_PACK` and an `evaluate_scrnaseq_plausibility` wrapper
modeled exactly on `verification/rnaseq_plausibility.py`, gated to `assay == "scrnaseq"`
in `_discover_qc`, capped at WARN, emitting explicit `unverified` for any absent metric.

Start with the metrics the standard nf-core/scrnaseq MultiQC actually reports
(recovered-cell band, fraction-reads-in-cells as a knee-point proxy) and **defer**
mito-fraction / doublet-rate if they require a downstream compute path the base
pipeline doesn't run. Verify slug availability early, since unconfirmed slugs will all
degrade to UNVERIFIED.

Build **test-first** with synthetic metric fixtures inside and outside each band (no real
nf-core run in CI), matching how the v0.6.0 RNA-seq plausibility slice shipped.

## Why this was picked (moat grounding)

- **Not shipped, not blocker-deferred.** `CAPABILITY_ROADMAP.md:322–325` specs the
  single-cell checks (doublet-rate band, mito-fraction distribution, knee-point sanity,
  recovered-cell band) and line 306 marks them deferred to "a later slice" — a slice, not
  a blocker. `runner.py:114–120` confirms the `scrnaseq` plausibility slot is empty.
- **Deepens the moat's strongest axis** — "the verdict gets smarter about biology"
  (`CAPABILITY_ROADMAP.md:313`) — and does it **depth-first on an assay already on the
  engine** (`USE_CASE_UNIVERSE.md:68`), so no demand-pull and no new-assay integration risk.
  Captures per-assay plausibility distributions into the eval corpus (moat #2).
- **Clear, testable slice today**, reusing the germline/RNA-seq pattern: a
  `*_PLAUSIBILITY_PACK`, a wrapper that emits explicit `unverified` for absent metrics
  (`rnaseq_plausibility.py`), fixtures inside/outside each band, no real nf-core run in CI.

## Known caveat (feasibility)

The real open question is **which metric slugs nf-core/scrnaseq's MultiQC actually
emits.** Recovered-cell count and fraction-reads-in-cells are standard STARsolo/cellranger
QC; **mito-fraction and doublet-rate often need a downstream step (scanpy/scDblFinder)
the base pipeline may not run** — so those two may need deferring or degrade to UNVERIFIED.
That is acceptable and by-design: the same UNVERIFIED-when-absent contract that carried the
RNA-seq slice absorbs unknown/wrong slugs, so the slice is buildable and testable
regardless. Bands are uncalibrated engineering defaults, WARN-capped, no FAIL until real
data — same posture as every prior plausibility slice.

## Guardrails (must hold)

- Layer-2 only (verify), no Layer-1 workflow authoring.
- No raw-read egress — operates on already-ingested MultiQC metrics on the user's compute.
- No correctness over-claiming — WARN-capped, UNVERIFIED never rendered as PASS.
- Research-use only; a single-cell verdict means "ran correctly and reproducibly."
- Test-first; no real nf-core run in CI.

## Alternates considered (not picked)

- RNA-seq concordance autorun (C1 follow-on) — lower risk but narrower (automates an
  already-shipped manual concordance).
- C6 slice 2 (held-out accuracy trend) — folding C1/C3 unlabeled signals is blocked on a
  labeling design; slice 1 just shipped (v0.17.0).
