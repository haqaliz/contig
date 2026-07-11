# Aspect: verdict-wiring

## Problem slice & outcome

The `sex_plausibility` result reaches the verdict on every germline run, and provably
cannot change the exit code. Small, surgical: one gate extension + one integration test.

## In scope

- In `src/contig/runner.py` `_discover_qc`, the existing germline block (`runner.py:254-264`,
  `if assay == "variant_calling"`): after `evaluate_variant_plausibility(vcfs[0])`, add
  `results.extend(evaluate_sex_plausibility(vcfs[0]))`. **Reuse the same located `vcfs[0]`** —
  no second rglob/discovery.
- Import `evaluate_sex_plausibility` beside `runner.py:60`
  (`from contig.verification.sex_plausibility import evaluate_sex_plausibility`).
- Honest skip: when no VCF is located, the block already falls through silently (structural
  QC owns the missing-required-output case) — no false UNVERIFIED added here.

## Out of scope

- The inference logic (aspect inference-core).
- Provenance capture / methods / HTML (aspect provenance-surfacing).
- `contig verify` — it does not re-run QC packs; the check flows via the `run` path only.

## Acceptance criteria (testable)

- An integration test exercising `_discover_qc(run_dir, "variant_calling")` (or the nearest
  existing germline `_discover_qc` test harness) with a discordant VCF fixture placed at the
  manifest's required glob → the returned `results` contain a `sex_plausibility:*` WARN and
  an `x_het_ratio:*` informational result, **alongside** the existing `ts_tv`/`het_hom`
  results (no regression to those).
- A non-germline assay (e.g. `rnaseq`) run through `_discover_qc` → **no** `sex_plausibility`
  result (gate holds).
- Verdict-invariance: with only a WARN `sex_plausibility` present, `overall_verdict` is at
  most `warn`; assert `contig run`'s exit path (`cli.py:610-612`) is unaffected (a WARN
  verdict does not `raise typer.Exit`). Cover via the existing verdict/exit test pattern.
- Full suite stays green: `uv run pytest`.

## Dependencies & sequencing

- Depends on: **inference-core** (imports `evaluate_sex_plausibility`). Sequence after it.
- Independent of provenance-surfacing (can land before or after it).

## Risks specific to this aspect

- Locating the correct existing `_discover_qc` germline test to extend rather than
  duplicating harness — the dig points at the `variant_calling` gate at `runner.py:254-264`;
  find its current test in `tests/` first (RED).
