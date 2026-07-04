# Task 2 report — Phase 2: auto-wire concordance into the somatic verdict

Branch `feat/somatic-concordance/aliz`. Strict TDD (RED confirmed via ImportError
before any production code, then GREEN, then a light REFACTOR pass — comments
only, no behavior change).

## Files changed

- `src/contig/verification/somatic_concordance.py` — added `select_caller_vcfs`
  and `evaluate_somatic_concordance_from_run`.
- `src/contig/runner.py` — one new import + one `results.extend(...)` line in
  `_discover_qc`'s somatic branch.
- `tests/verification/test_somatic_concordance.py` — 8 new unit tests for the
  two helpers (RED first).
- `tests/verification/test_run_qc.py` — 5 new `_discover_qc` gating tests (RED
  first).

## Public API added (`somatic_concordance.py`)

```python
def select_caller_vcfs(
    run_dir: str | os.PathLike, vcfs: Iterable[str | os.PathLike]
) -> tuple[list[Path], list[Path], str | None]: ...

def evaluate_somatic_concordance_from_run(
    run_dir: str | os.PathLike, vcfs: Iterable[str | os.PathLike]
) -> list[QCResult]: ...
```

`select_caller_vcfs` matches `"mutect2"` / `"strelka"` as lowercased path
components below `run_dir` (mirrors the existing Mutect2 match in `runner.py`).
If either caller's VCFs span more than one distinct `p.parent.name` (pair dir),
it returns `([], [], reason)` instead of guessing which pair to compare.

`evaluate_somatic_concordance_from_run` calls `select_caller_vcfs`; on a
`reason` it emits one `somatic_site_overlap` UNVERIFIED result; if either
caller's list is empty it returns `[]` (clean skip); otherwise it delegates to
`evaluate_somatic_concordance(mutect2, strelka)` from Phase 1.

## Exact `_discover_qc` insertion (`src/contig/runner.py`)

Import (alongside the other verification imports, `runner.py:31`):

```python
from contig.verification.somatic_concordance import evaluate_somatic_concordance_from_run
```

Inside the existing `if assay == "somatic_variant_calling":` branch, inside
`if vcfs:`, immediately after the VAF-plausibility mutect2/else block (the
plausibility block itself is untouched):

```python
            # Cross-tool PASS-site-overlap concordance (Strelka2 vs Mutect2):
            # appended after, and independent of, VAF plausibility above — it
            # reuses the same globbed VCF list but self-selects both callers'
            # files and skips cleanly (or reports UNVERIFIED) on its own terms.
            results.extend(evaluate_somatic_concordance_from_run(run_dir, vcfs))
```

## Test command and result

RED (before implementing the two helpers):

```
uv run pytest tests/verification/test_somatic_concordance.py tests/verification/test_run_qc.py -q
```
→ `ImportError: cannot import name 'evaluate_somatic_concordance_from_run' from
'contig.verification.somatic_concordance'` (collection error, confirming RED).

GREEN (after implementing):

```
uv run pytest tests/verification/test_somatic_concordance.py tests/verification/test_run_qc.py -v
```
→ `43 passed in 0.11s`

Full suite (regression check):

```
uv run pytest
```
→ `1068 passed, 1 skipped in 10.83s` (baseline after Task 1 was 1056 passed, 1
skipped, 0 failed) — strictly more passed, same skip count, zero failures.

## Deviations from the plan

None of substance. Test fixture details (VCF row helpers, sarek tree builder
`_sarek_tree`/`_pair_dir` in `test_somatic_concordance.py`,
`_pass_site_rows`/`_write_pass_vcf_gz` in `test_run_qc.py`) were written fresh
per-file rather than importing across test files, matching each file's existing
self-contained fixture style (mirrors how `test_run_qc.py` already keeps its own
`_write_vcf`/`_write_vcf_gz` helpers separate from `test_somatic_concordance.py`'s).

## Concerns

None blocking. Two pre-existing worktree-local modifications
(`docs/planning/_card/issue.md`, `docs/planning/_card/understanding.md`) were
present before this task started and are unrelated to Phase 2 — left untouched
and excluded from this commit.

## Fix wave

Folded in two Minor findings from the final review, both in
`src/contig/verification/somatic_concordance.py`. Strict TDD: failing tests
added first (confirmed RED), then the fixes, then full-suite green.

**Finding 1 (correctness) — cross-caller pair mismatch.** `select_caller_vcfs`
previously only flagged ambiguity when a single caller spanned >1 distinct pair
directory. It missed the case where Mutect2 has exactly one pair dir and
Strelka has exactly one pair dir but they're *different* pairs (e.g. Mutect2
only `T1_vs_N`, Strelka only `T2_vs_N`) — comparing those would corroborate two
unrelated tumor-normal pairs and read as a misleading WARN. Fixed by, after the
existing per-caller `> 1 distinct pair dir` check, also comparing the two
callers' single pair-dir sets: if both are non-empty and differ, return a
reason. `evaluate_somatic_concordance_from_run` reuses its existing single
`somatic_site_overlap` UNVERIFIED path for this reason (value `None`,
`kind="concordance"`) — no new branch needed there. Existing behavior
unchanged: same-pair single-pair runs, a caller spanning >1 pair, and a single
caller present (clean `[]` skip) all behave as before.

**Finding 2 (cosmetic) — round-then-compare.** `evaluate_somatic_concordance`
rounded the Jaccard to 4dp *before* the `< _OVERLAP_WARN_BELOW` band check, so
a value like `1808/2009 = 0.89995022...` (unrounded, correctly WARN) would
round to display `0.9` and read as PASS under the old rounded-first order.
Reordered to match germline `concordance.py:223`: compute `status` from the
unrounded `jaccard`, then round only the `value` placed on the `QCResult`.

### Covering tests

- `tests/verification/test_somatic_concordance.py`:
  - `test_select_caller_vcfs_single_pair_mismatch_is_ambiguous` — Mutect2
    `T1_vs_N`-only vs Strelka `T2_vs_N`-only → `([], [], reason)` with both pair
    names in `reason`.
  - `test_evaluate_somatic_concordance_from_run_pair_mismatch_is_unverified` —
    same setup → one UNVERIFIED `somatic_site_overlap` result, `value=None`,
    `kind="concordance"`.
  - `test_warn_band_computed_on_unrounded_jaccard` — constructed
    shared=1808/union=2009 (unrounded Jaccard `0.89995022...`, `round(..., 4)
    == 0.9`) → asserts `status == "warn"` even though the rounded `value ==
    0.9`, proving the band is decided pre-rounding.

All three failed (confirmed RED) before the fixes and pass after.

### Test commands and results

RED:
```
uv run pytest tests/verification/test_somatic_concordance.py -q
```
→ 3 of the (then) 25 tests failed with the expected assertion mismatches
(`mutect2 == []` false, `status == 'unverified'` got `'pass'`,
`status == 'warn'` got `'pass'`).

GREEN (targeted):
```
uv run pytest tests/verification/test_somatic_concordance.py -q
```
→ `25 passed`

GREEN (full suite):
```
uv run pytest
```
→ `1071 passed, 1 skipped in 10.96s` (prior baseline 1068 passed, 1 skipped, 0
failed — 3 more passed from the new tests, same skip, zero failures).

No other files were touched; `runner.py` and the WARN-capped / `kind="concordance"`
posture are unchanged.
