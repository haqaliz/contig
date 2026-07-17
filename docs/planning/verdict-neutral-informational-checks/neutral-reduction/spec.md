# Aspect spec: neutral-reduction

Parent PRD: `docs/planning/verdict-neutral-informational-checks/prd.md`.
Single aspect for this card (matching the repo's one-aspect-per-card precedent).

## Problem slice and user outcome

A Contig `pass` can be produced by checks that assert nothing. After this aspect, a `pass`
means **at least one check that could have failed, didn't** — and the dashboard stops
printing a false-pass sentence for runs the engine called `unverified`.

## In scope

- **R1** `informational: bool = False` on `QCResult` (additive; `QCKind` precedent).
- **R2** Mark all four informational checks: `duplication_rate` (band-less config),
  `gene_symbol_concordance`, `x_het_ratio`, `gene_overlap` (hardcoded pass).
- **R3** `overall_verdict` ignores informational results for positive severity; a set of
  only informational/unverified reduces to `unverified`.
- **R4** Informational results are distinguishable from an asserting pass in the text
  report, HTML report, `contig methods`, and the dashboard.
- **R5** Fix `dashboard/lib/derive.ts::overallQc`'s missing `unverified` arm.
- **R6** Back-compat: pre-change bundles reduce to their existing verdict.
- **R7** An enumeration guard so a fifth informational check cannot land silently.
- **Measurement:** the verdict-flip count across the fixture corpus (PRD "Goals").

## Out of scope

Per PRD: `runner.py:412`'s `multiqc is not None` gate; re-opening any declined-by-design
band; `pon_applied`; de-duplicating `QC_RANK`/`STATUS_RANK`; zod validation; `percent_rRNA`.

Additionally **not** in scope: reclassifying `min_sample_count` (PRD Open Q5) — it can fail,
so it stays asserting. Any "asserts something biological" distinction is a follow-on.

## Acceptance criteria (testable)

- **A1** `QCResult(...).informational is False` by default; a record serialized without the
  field deserializes with `informational=False`.
- **A2** `overall_verdict([informational pass])` → `"unverified"` (NOT `"pass"`).
- **A3** `overall_verdict([informational pass, asserting pass])` → `"pass"`.
- **A4** `overall_verdict([informational pass, unverified])` → `"unverified"`.
- **A5** `overall_verdict([])` still raises `ValueError` (unchanged).
- **A6** An asserting `fail`/`warn` still dominates regardless of informational results.
- **A7** Each of the four checks emits `informational=True`; a test enumerates the exact
  set so adding a fifth without updating it fails (R7).
- **A8** A band-less rule is detected by absence of **all four** bound keys — NOT by
  `expected_range is None`. A rule with only `fail_below` is **not** informational and can
  still FAIL (regression test).
- **A9** A pre-change `run_record.json` fixture (no `informational` key) round-trips and
  yields its original verdict.
- **A10** `overallQc([all unverified])` → `"unverified"`; `explainVerdict` does not return
  `"PASS: all N checks passed"` for such a run.
- **A11** `x_het_ratio` with `value=None` (ratio unavailable) → `"unverified"`, not an
  informational pass (see Open Q below).
- **A12** `uv run pytest` green; dashboard `npm run build` + tests green.

## Dependencies and sequencing

1. R1 (model) → R3 (reducer) → R2 (mark checks) → R4 (render) → R7 (guard).
2. R5 (dashboard) is independent of the Python work and can proceed in parallel.
3. The corpus-flip measurement must run **after** R2/R3 and **before** the CHANGELOG is
   written — its number decides how the slice is described.

## Open questions / risks specific to this aspect

- **`x_het_ratio` conflates two states (A11).** `sex_plausibility.py:303-312` returns
  `status="pass"`, `value=None` when the ratio is *unavailable* — a check that could not
  compute, reporting a pass. `tests/verification/test_sex_plausibility.py:435` is named
  `test_evaluate_indeterminate_is_unverified_with_none_value` yet asserts `pass`: the author
  felt the tension. **Decision for this aspect:** `value is None` → `unverified`; a real
  value → informational pass. This is a behaviour change beyond a pure marker addition —
  flag at the Phase 3 checkpoint if it looks larger than expected.
- **~20 tests pin informational→pass.** Each must be rewritten to the new intent, never
  weakened or deleted. This is the highest-risk part of the aspect.
- **Expected measurement:** zero flips for RNA-seq (`min_sample_count` floors it), non-zero
  for the other six assays. If zero everywhere, say so plainly in the CHANGELOG.
