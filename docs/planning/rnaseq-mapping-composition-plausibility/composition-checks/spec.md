# Aspect spec: composition-checks

Parent PRD: `../prd.md`. The single aspect of this slice — it builds as one cohesive
unit (parser → rule pack → gate → tests), so there is one aspect, one plan.

## Problem slice & user outcome

A completed RNA-seq run's verdict gains a **read-composition** axis: three per-sample,
WARN-capped checks (`exonic_fraction`, `intronic_fraction`, `unassigned_fraction`)
computed from the RSeQC `read_distribution.txt` the run already produced, so a
gDNA-contaminated / poorly-enriched library is caught instead of silently "passing".

## In scope

- `verification/rnaseq_metrics.py::parse_read_distribution(path) -> dict[str, float]`
  (stdlib-only, pure, omit-never-guess, independent per-metric computation).
- `RNASEQ_COMPOSITION_PACK` (3 WARN-capped rules) in `rule_pack.py`, not in `_RULE_PACKS`.
- `_locate_rnaseq_composition_qc(run_dir)` + an additive `_discover_qc` gate for
  `assay == "rnaseq"`, emitting `rnaseq_composition_qc:<sample>` UNVERIFIED on
  located-but-empty; silent skip when no artifact.
- Unit + gate tests; a committed `tests/fixtures/rnaseq/` read_distribution fixture.

## Out of scope (this aspect)

- Gene-body-coverage evenness; FAIL severity; dashboard card; launch-seam changes;
  cross-sample aggregation; adding `rnaseq` to `_DEDICATED_METRIC_ASSAYS`.

## Acceptance criteria (testable)

1. `parse_read_distribution` on a healthy fixture returns the three fractions with the
   documented formulas; on the yeast test artifact exonic≈0.9998, intronic≈0.0002,
   unassigned≈0.11 (all PASS).
2. A low-exonic / high-intronic / high-unassigned fixture drives the matching check to
   WARN with value + expected range; a healthy one is PASS.
3. Missing preamble line or missing Group row → that metric omitted (not 0); zero
   denominator → omitted. All three uncomputable → located-but-empty → one
   `rnaseq_composition_qc:<sample>` UNVERIFIED.
4. `_discover_qc(run_dir, "rnaseq")` emits the three checks when the artifact is present;
   `_discover_qc(run_dir, "variant_calling")` (or any non-rnaseq) emits none of them.
5. No artifact anywhere under the run → no composition check emitted (silent skip).
6. Both a `results/` and a `work/` copy present → exactly one result per sample
   (discovery deduped / preferring the published tree).
7. Full suite green (baseline 1452 passed, 1 skipped); no new dependency; no real
   nf-core run in CI.

## Dependencies & sequencing

Parser (Phase 1) → rule pack (Phase 2) → gate + locator (Phase 3) → committed fixture +
integration test (Phase 4). Phases 1–2 are independent and can run in parallel; Phase 3
depends on both; Phase 4 depends on Phase 3.

## Aspect-specific risks

- Duplicate `*.read_distribution.txt` under `work/` and `results/` (AC6) — pin discovery.
- Two different denominators (assigned vs total) — require an inline comment so a future
  maintainer doesn't "unify" them.
