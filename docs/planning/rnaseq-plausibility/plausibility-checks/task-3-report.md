# Task 3 Report — Phase 3: Wire into `_discover_qc`

Date: 2026-06-28
Branch: `master` (worktree `feat-rnaseq-plausibility`)
Status: DONE

---

## Changes made

### `src/contig/runner.py`

Two additions:

1. Imports at module top (alongside existing verification imports):
   ```python
   from contig.verification.qc_ingest import parse_multiqc_general_stats_file
   from contig.verification.rnaseq_plausibility import evaluate_rnaseq_plausibility
   ```

2. Block added in `_discover_qc`, after the existing germline (`variant_calling`) block:
   ```python
   if assay == "rnaseq" and multiqc is not None:
       metrics = parse_multiqc_general_stats_file(multiqc)
       results.extend(evaluate_rnaseq_plausibility(metrics))
   ```
   Gate is strict: fires only when `assay == "rnaseq"` AND a MultiQC report was
   found (the `multiqc` local already holds the resolved path or `None`).

### `tests/verification/test_run_qc.py`

Two new tests added before the existing VCF/concordance section:

- `test_discover_qc_emits_rnaseq_plausibility_for_rnaseq_assay` — builds a
  tmp run dir with `multiqc_data.json` carrying `percent_duplication: 95.0` for
  sample `S1`; calls `_discover_qc(run_dir, assay="rnaseq")`; asserts
  `duplication_rate:S1` is present and has `status="warn"` (95.0 > 80.0 band).

- `test_discover_qc_does_not_emit_rnaseq_plausibility_for_non_rnaseq_assay` —
  same run dir; calls with `assay="variant_calling"`; asserts no
  `duplication_rate:*` or `rrna_contamination:*` check appears (gate works).

---

## TDD trace

RED: first test (`emits_rnaseq_plausibility_for_rnaseq_assay`) failed with
`AssertionError: 'duplication_rate:S1' not in {'min_sample_count': ...}`.
Second test (gating) already passed by absence — correct for a gate test.

GREEN: added two imports and the `if assay == "rnaseq" and multiqc is not None`
block. Both tests passed.

REFACTOR: none needed.

---

## Test command and output

```
uv run pytest tests/verification/test_run_qc.py -v
```
14 passed (12 pre-existing + 2 new).

```
uv run pytest -q
```
**827 passed, 1 skipped** (baseline was 825 passed + 1 skipped; delta = +2).

No detector-eval or corpus changes (plausibility is not a `FailureClass`).

---

## Commit SHA

(filled in after commit)
