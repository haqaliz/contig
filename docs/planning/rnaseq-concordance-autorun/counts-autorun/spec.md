# Aspect spec — counts-autorun

Parent PRD: `../prd.md` · slug `rnaseq-concordance-autorun` · aspect `counts-autorun`

## Problem slice & user outcome

The single aspect of this feature: `contig verify <run> --concordance-counts-auto --reads
<sheet> --index <kallisto-index>` runs a second quantifier (kallisto) behind an injectable
seam, collapses its transcript-level output to a gene-count matrix, and corroborates the
run's primary Salmon gene matrix against it — turnkey, no user-produced matrix.

## In scope

- New `src/contig/verification/count_quantifier.py` seam (mirrors `second_caller.py`).
- New `_evaluate_run_counts_concordance_auto` in `cli.py` (mirrors
  `_evaluate_run_concordance_auto`).
- New `verify` CLI options `--concordance-counts-auto` / `--reads` / `--index`; 4-way
  mutual-exclusion guard.
- A **pure, CI-tested** transcript→gene collapse (`collapse_to_gene`) + t2g resolver.
- Tests: seam unit tests + CLI integration tests (injected fake quantifier).
- Docs: `verify` docstring, mutual-exclusion message, CHANGELOG Unreleased.

## Out of scope

- Executing kallisto in CI (seam injected; real tool never run).
- Persisted-sheet `--reads` fallback; `--transcriptome` in-seam index build.
- Single-cell concordance; dashboard label; FAIL severity.
- Any verdict/exit/record/reproduce change.

## Acceptance criteria (testable)

1. Concordant injected matrix → PASS concordance checks; divergent → WARN; exit 0 in both.
2. Missing `--reads` or `--index`, quantifier failure, non-rnaseq run → skip note, zero
   checks, exit unchanged.
3. `--concordance-counts-auto` + any other concordance flag → exit 1, "choose one" message.
4. `kallisto_command` argv builder asserted (never executed); `collapse_to_gene` correctness
   asserted on synthetic transcript counts + t2g (real, in CI).
5. Full suite green; no existing verdict/exit behavior changes.

## Dependencies & sequencing

Phase 1 (seam) → Phase 2 (CLI wiring, depends on the seam) → Phase 3 (docs). Reuses shipped
`evaluate_count_concordance`, `_resolve_primary_counts`, `_COUNT_MATRIX_GLOB`, `fastq_paths`.

## Aspect-specific risks

- The transcript→gene collapse is the scientific substance; keep it a pure function so it is
  CI-tested (mitigates the PRD's gap #1 — a wrong collapse would make every real run
  UNVERIFIED).
- kallisto's exact quant argv is best-effort (never run in CI); assert shape, not behavior.
