# Phase 4 (M3) report — wire annotation plausibility into `_discover_qc` for both variant assays

- **Slug/aspect:** `annotation-plausibility` / `verify`
- **Plan:** `docs/planning/annotation-plausibility/verify/plan_20260710.md` → "Phase 4 (M3)"
- **Scope:** `src/contig/runner.py` only (+ tests). No changes to `registry.py`,
  `self_heal.py`, `rule_pack.py`, or `annotation_plausibility.py`.

## What already existed

`_discover_qc`'s annotation-structural block (Phase 1, `runner.py:139-156` before this
change) was already gated to `assay in VARIANT_ASSAYS` (`registry.VARIANT_ASSAYS =
("variant_calling", "somatic_variant_calling")`). It performed a single
`sorted(run_dir.rglob("*.vcf.gz"))` scan, took the first VCF whose
`annotation_metrics(vcf).info_key is not None` (i.e. header declares CSQ or ANN), ran
`evaluate_annotation_structural(vcf)` over it, and `break`s. Phase 2/3 had already shipped
`annotation_plausibility_metrics` / `evaluate_annotation_plausibility` (WARN-capped,
never-a-false-pass) but nothing called them from the real verdict path.

## RED

Extended both integration test files with plausibility assertions before touching
`runner.py`, confirmed they failed with `StopIteration` (checks not emitted):

- `tests/test_annotation_integration.py`:
  - `test_annotated_germline_run_verifies_and_captures_provenance` — added assertions
    that `annotation_real_fraction:sample` and `annotation_consequence_distribution:sample`
    are present and `pass` (mixed missense/synonymous fixture → real_fraction 1.0,
    intergenic_fraction 0.0, both in-band).
  - New `test_all_intergenic_germline_run_warns_but_never_fails` — an all-
    `intergenic_variant` CSQ fixture → `annotation_consequence_distribution:sample`
    is `warn` and asserted `!= "fail"` (WARN-cap holds through the real verdict path).
  - `test_unannotated_germline_run_yields_no_false_pass` — strengthened: beyond
    "no annotation_* check reports pass," added an explicit assertion that
    **no** `annotation_real_fraction` / `annotation_consequence_distribution` check
    (any status, including `unverified`) is emitted at all for an un-annotated run —
    confirming the "skip silently, no duplicate UNVERIFIED" behavior from the plan.
- `tests/test_annotation_somatic_gate.py`:
  - `test_annotated_somatic_run_verifies` — added the same real_fraction/distribution
    pass assertions for the somatic sarek-shaped fixture
    (`results/annotation/tumorA_vs_normalA/mutect2/tumorA_VEP.ann.vcf.gz`).
  - `test_unannotated_somatic_run_yields_no_false_pass` was already generic enough
    (filters on `check.startswith("annotation_")`) to cover the plausibility checks
    without modification; left as-is.

Ran `uv run pytest tests/test_annotation_integration.py tests/test_annotation_somatic_gate.py -q`
before wiring: 3 failures (`StopIteration` on the new `next(...)` lookups), confirming RED.

## GREEN + REFACTOR (combined — single-lookup form from the start)

In `src/contig/runner.py`, inside the existing `if assay in VARIANT_ASSAYS:` block, added
one import (`evaluate_annotation_plausibility` from
`contig.verification.annotation_plausibility`) and one line inside the existing loop body,
so the same located VCF feeds both verifiers with no second `rglob`/CSQ-scan:

```python
for vcf in sorted(run_dir.rglob("*.vcf.gz")):
    if annotation_metrics(vcf).info_key is not None:
        results.extend(evaluate_annotation_structural(vcf))
        results.extend(evaluate_annotation_plausibility(vcf))
        break
```

The plan's REFACTOR step (collapse the duplicate rglob+CSQ-scan) was folded directly into
GREEN since the structural block's single-lookup loop already existed — there was nothing
to duplicate and then collapse; extending the same loop body was the minimal-and-final form.
Updated the surrounding comment block to describe both structural and plausibility checks
sharing the one located VCF, and to state explicitly that an un-annotated run causes both
blocks to skip silently (no duplicate UNVERIFIED).

Structural behavior (`annotation_present`, `annotation_complete`) is untouched — same call,
same position, same break — so existing structural assertions continue to pass unmodified.

## Validation

- `uv run pytest tests/test_annotation_integration.py tests/test_annotation_somatic_gate.py -q`
  → **9 passed**.
- Full suite: `uv run pytest -q` → **1285 passed, 1 skipped** (the skip is the pre-existing
  `tests/test_signing.py:55` "cryptography is installed" skip, unrelated to this change).
- No changes to `src/contig/data/*baseline*` or corpus files; `eval-guard`/`heal-guard`
  detector machinery untouched.

## Commit

`feat(verify): wire annotation plausibility into the verdict for both variant assays [C7 M3]`
