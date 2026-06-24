# C1 — Cross-tool concordance verification

Source: no GitHub issue. Inline brief, owner `aliz`, branch `feat/concordance/aliz`.
Origin: `docs/technical/CAPABILITY_ROADMAP.md` capability C1 (the chosen lead), plus
the engine investigation captured in the working session.

## Brief

Add a new verification axis to the verified verdict: run a **second, independent
tool** on the same input as the primary pipeline and treat agreement between the
two as corroboration of the result. Disagreement is surfaced honestly and moves
the verdict, never hidden.

This is distinct from the already-shipped `contig benchmark`, which compares a run
to a designated **reference run** of the same pipeline. Concordance compares **two
different tools on the same data within one analysis**, so it catches tool-specific
error even when no reference run exists.

Lead assay: **germline variant calling** (already on the engine), where the metric
is clearest: genotype concordance between two call sets. RNA-seq quantification
(per-gene rank correlation) and single-cell come later, same mechanism.

## Why it is the moat

No incumbent issues a correctness verdict at all, let alone a cross-tool one.
Concordance is a defensible verification primitive, it produces rich evaluation
data (agreement distributions per assay), and it gets better as models get better
at adjudicating why two tools disagree.

## Investigation findings (from the session, to confirm in Phase 2)

- `QCResult.kind` already discriminates `"metric" | "structural"` (`src/contig/models.py`).
  Concordance is a third kind; a concordance `QCResult` flows through
  `overall_verdict` unchanged (a `fail` dominates a `warn`, a `warn` a `pass`).
- Pattern to mirror: `src/contig/verification/structural.py` (a `_structural()`
  tagging helper; per-assay manifests via `manifest_for(assay)`). Add
  `src/contig/verification/concordance.py` the same shape.
- Seam to wire into: `src/contig/verification/run_qc.py` (assay-gated, exactly like
  `cross_sample` is gated there today).
- Surface: a "corroborated by" line in `contig show` naming the metric and the
  second tool.

## Scope guardrails (from CLAUDE.md / FEATURES.md / USE_CASE_UNIVERSE.md)

- Concordance is **corroboration, not ground truth**. It can move a verdict to WARN.
  It never alone promotes UNVERIFIED to PASS.
- No raw-read egress; the second tool runs on the user's compute.
- No clinical claim. A verdict means "ran correctly and reproducibly," scoped per
  assay.
- Test-first: every piece lands with its failing test written first.

## Open questions for the interview

- For the first slice, do we compute the metric on **two call sets the engine
  produced** (primary plus a second caller actually run), or start with the pure
  metric function over two given call sets and defer the second-caller execution?
- WARN vs FAIL threshold for genotype concordance, and whether it is ever FAIL or
  always at most WARN in the first slice.
- Which second germline caller to standardize on (for example bcftools call vs
  the primary GATK HaplotypeCaller).
