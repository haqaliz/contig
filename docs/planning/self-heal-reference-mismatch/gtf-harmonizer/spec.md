# Aspect spec — gtf-harmonizer

The single aspect of `self-heal-reference-mismatch`: a pure GTF-seqname harmonizer
wired into the v0.7.0 pre-flight gate to auto-recover a `chr`-prefix-asymmetric
contig-naming mismatch.

## Problem slice & user outcome

A run blocked *only* by a `chr`-prefix-asymmetric FASTA/GTF mismatch completes
unattended (the GTF is rewritten to match the FASTA), instead of exiting 1 — with the
rewrite visible on the verdict surface and reproducible via `rerun`/`resume`.

## In scope

- Pure decision + transform module (`reference_harmonize.py`): decide if a **safe**
  uniform `chr` add/strip on the GTF resolves the mismatch; if so, stream-rewrite the
  GTF (column 1 only, byte-faithful elsewhere, gzip-transparent) to run scratch.
- Gate integration at `_dispatch_run`: auto-harmonize + proceed; refuse honestly when no
  safe transform exists; honor `--allow-reference-mismatch` unchanged.
- Provenance: `LaunchManifest.harmonized_reference` (+ direction), `ReferenceIdentity`
  harmonized fields in `run_record.json`; reproduce the **decision** (re-derive at
  dispatch; manifest keeps the **original** GTF path).
- Verdict breadcrumb: a WARN-level QC check that the GTF was harmonized.

## Out of scope

- Assembly-signature (sample-vs-reference) repair; per-contig name mapping (chrM↔MT);
  fabricating/downloading a genome; rewriting the FASTA; a runtime `reference_mismatch`
  FailureClass / `detector_corpus.jsonl` case; known-sites; GTF version.

## Acceptance criteria (testable)

1. A disjoint `chr`-asymmetric pair → `plan_harmonization` returns a plan with the
   correct direction; a genuine wrong-assembly disjoint pair → returns `None` (refuse).
2. The harmonized GTF, fed back through `check_reference_consistency(fasta, harmonized)`,
   returns `[]` (closed loop — mismatch resolved, M7).
3. The rewrite changes only column 1; columns 2-9, `#`/`track`/`browser` lines, and
   line endings are byte-identical; `.gz` in → `.gz` out (M8).
4. A run on a chr-asymmetric pair proceeds (no `Exit(1)`), points the pipeline at the
   harmonized GTF, and prints a plain-language note.
5. `rerun`/`resume` reproduce the harmonization decision (re-derive); the manifest stores
   the original GTF path + `harmonized_reference=True`.
6. A harmonized run carries a WARN-level "reference harmonized" check on its verdict;
   `ReferenceIdentity` in `run_record.json` records `harmonized` + direction.
7. Existing `tests/test_reference_check.py` and the full suite stay green; no real
   nf-core/samtools run in CI.

## Dependencies & sequencing

Phases 1→2 (pure module) have no deps; Phase 3 (models) is additive; Phase 4 (gate)
depends on 1-3; Phase 5 (breadcrumb) depends on 3-4. See `plan_20260630.md`.

## Aspect-specific risks

- Over-eager harmonization (manufactures a silent wrong result) — gated by the
  post-transform-intersection predicate (acceptance 1-2).
- Verdict breadcrumb dragging a legit run to WARN — accepted per Contig's conservative
  ethos (harmonization is a caveat the scientist should consciously accept); flagged as a
  review checkpoint in the plan.
