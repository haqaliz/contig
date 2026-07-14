# Task A report — swap-verdict, Phases 1-3

Implements the tumor/normal swap smell test per
`docs/planning/somatic-swapped-pair/swap-verdict/plan_20260714.md` and
`docs/planning/somatic-swapped-pair/swap-verdict/spec.md`. Phases 1, 2, 3 only
(code). Phase 4 (docs sync: CHANGELOG.md, CAPABILITY_ROADMAP.md, FEATURES.md)
is explicitly out of scope for this task and was not touched.

Strict RED -> GREEN TDD followed for every phase: failing test(s) written
first (confirmed to fail on missing import / assertion), then minimum
production code added, then the phase's test file re-run green, then the
full suite re-run green before moving on.

## Files changed

- `src/contig/verification/somatic_plausibility.py` — new resolver, reader,
  and evaluator (Phases 1-2).
- `src/contig/verification/rule_pack.py` — new `normal_median_vaf` rule on
  `SOMATIC_PLAUSIBILITY_PACK` (Phase 2).
- `src/contig/runner.py` — import + wiring in the `somatic_variant_calling`
  block (Phase 3).
- `tests/verification/test_somatic_plausibility.py` — resolver tests,
  evaluator tests, `_header()` extended with a `normal_line` param (Phases
  1-2).
- `tests/verification/test_run_qc.py` — somatic-run wiring test (Phase 3).

## New functions

### Phase 1 — `src/contig/verification/somatic_plausibility.py`

```python
def _normal_column_index(header_lines: list[str]) -> int | None
```
Resolves the NORMAL column index from `##normal_sample=<name>` + the
`#CHROM` line. Mirrors `_tumor_column_index`. Returns `None` if either the
header line or the named column is absent — never a positional guess.

```python
def _normal_sample_name(header_lines: list[str]) -> str | None
```
Returns the `##normal_sample=` value, or `None` if the header line is
absent. Mirrors `_tumor_sample_name`.

### Phase 2 — `src/contig/verification/somatic_plausibility.py`

```python
def _read_normal(vcf_path: str | os.PathLike) -> tuple[list[float], int, int | None]
```
Streams a somatic VCF and returns `(normal VAFs, considered biallelic record
count, normal column index)`. A clone of `_read_somatic` resolving via
`_normal_column_index` instead of `_tumor_column_index` — the "acceptable
simpler alternative" the plan allows in place of extracting a shared
`_read_column_vafs` helper, kept as a separate pass so `_read_somatic`
(the shipped tumor path) stays byte-identical. No REFACTOR-phase DRY was
applied; both tumor and normal readers currently duplicate the streaming
loop by design (plan explicitly permits deferring the DRY).

```python
def normal_median_vaf(vcf_path: str | os.PathLike) -> tuple[float | None, str | None]
```
Median VAF over the normal column (same biallelic record set, same
`_vaf_from_sample` derivation as the tumor metric), and the resolved normal
sample name (`None` when the column never resolved).

```python
def evaluate_swap_plausibility(vcf_path: str | os.PathLike, sample: str | None = None) -> list[QCResult]
```
Structurally mirrors `strelka_vaf.evaluate_strelka_vaf_plausibility`: builds
a `by_metric = {"normal_median_vaf": median}` dict, runs it through
`rule_pack.evaluate()` against `SOMATIC_PLAUSIBILITY_PACK` (isolation trick
— `evaluate()` skips any rule whose metric key is absent, so only
`normal_median_vaf` ever fires from this call), wraps each returned
result's message with a `"normal-sample VAF (tumor/normal swap check): "`
prefix (since `evaluate()` ignores the pack's own `"message"` field), and
appends one explicit `unverified` `QCResult` when `median is None` (no
`##normal_sample=` header, unmatched name, or no derivable normal VAF).

### Phase 2 — `src/contig/verification/rule_pack.py`

New entry appended to `SOMATIC_PLAUSIBILITY_PACK`:

```python
{
    "check": "normal_median_vaf",
    "metric": "normal_median_vaf",
    "warn_above": 0.30,
    "message": "median normal-sample variant allele fraction (high => possible tumor/normal swap or contamination)",
},
```
`warn_above` only, no `warn_below`, no `fail_*` — WARN-capped by
construction, matching the spec's acceptance criteria.

### Phase 3 — `src/contig/runner.py`

- Added `evaluate_swap_plausibility` to the existing
  `from contig.verification.somatic_plausibility import (...)` block.
- Inside `if assay == "somatic_variant_calling":` / `if mutect2 is not None:`,
  immediately after `results.extend(evaluate_somatic_plausibility(mutect2))`,
  added `results.extend(evaluate_swap_plausibility(mutect2))`, reusing the
  already-located `mutect2` path (no re-glob). Same "mutect2 found" gate, so
  a run with no Mutect2 VCF still skips silently.

## Tests added

`tests/verification/test_somatic_plausibility.py`:

- `_header()` gained a `normal_line=False` param that injects
  `##normal_sample=<normal>` when `True` (existing calls unaffected —
  default keeps prior behavior).
- Phase 1 (resolver):
  - `test_normal_column_index_found` — `##normal_sample=NORMAL` + matching
    `#CHROM` column resolves to index 9.
  - `test_normal_column_index_none_when_no_normal_sample_header` — header
    absent -> `None`.
  - `test_normal_column_index_none_when_name_not_in_chrom_columns` — header
    present but name not among `#CHROM` columns -> `None`.
  - `test_normal_sample_name_returns_header_value` — returns the header
    value.
  - `test_normal_sample_name_none_when_header_absent` — `None` when absent.
- Phase 2 (evaluator):
  - `test_swap_check_correct_pair_passes` — normal AF ~0.0 -> one
    `normal_median_vaf:NORMAL` check, status `pass`.
  - `test_swap_check_high_normal_warns` — normal AF ~0.45 -> status `warn`,
    message contains "swap".
  - `test_swap_check_unverified_when_no_normal_sample_header` — no
    `##normal_sample=` -> status `unverified`, `value=None`.
  - `test_swap_check_unverified_when_normal_column_has_no_derivable_vaf` —
    normal column resolves but FORMAT is GT-only (no AF/AD/DP) ->
    `unverified`, `value=None`.
  - `test_swap_check_isolation_emits_only_normal_median_vaf` — asserts the
    returned check-name prefix set is exactly `{"normal_median_vaf"}` (never
    `median_vaf`/`somatic_variant_count`/`strelka_median_vaf`).
  - `test_swap_check_gzip_supported` — `.vcf` and `.vcf.gz` inputs agree on
    status and value.
  - `test_swap_check_band_boundary` — normal median exactly `0.30` ->
    `pass`; `0.31` -> `warn`.

`tests/verification/test_run_qc.py`:

- `test_discover_qc_includes_swap_check_and_stays_warn_capped` — a somatic
  run dir with a Mutect2 VCF (under a `mutect2/` path) whose normal column
  carries AF ~0.45 yields exactly one `normal_median_vaf:NORMAL` `warn`
  check via `_discover_qc(..., assay="somatic_variant_calling")`, and
  `overall_verdict(results) != "fail"` (WARN-capped; exit-code/verdict
  reduction unaffected).

## Per-phase commits

| Phase | SHA | Message |
|---|---|---|
| 1 | `bcea2a0` | `feat(verify): resolve the normal-sample VCF column (somatic swap check)` |
| 2 | `6b6b55f` | `feat(verify): normal-sample median VAF swap smell test (WARN-capped)` |
| 3 | `c7cee63` | `feat(verify): wire normal_median_vaf swap check into the somatic QC gate` |

Range: `bd683f8..c7cee63` (`bd683f8` = pre-existing tip before this task).

## Final full-suite run

```
uv run pytest
...
1570 passed, 1 skipped in 12.18s
```

Baseline before this task: 1557 passed, 1 skipped. Delta: +13 passed (5
Phase 1 + 7 Phase 2 + 1 Phase 3), 0 failed, skip count unchanged.

## Acceptance criteria check (spec.md)

1. Correct pair (normal median VAF <= 0.10) -> PASS —
   `test_swap_check_correct_pair_passes` (AF 0.0).
2. Swapped/high-normal pair (~0.45) -> WARN, message names
   swap/mislabel/contamination — `test_swap_check_high_normal_warns`.
3. `##normal_sample=` absent/unparseable, or present-but-no-derivable-VAF ->
   UNVERIFIED — `test_swap_check_unverified_when_no_normal_sample_header`,
   `test_swap_check_unverified_when_normal_column_has_no_derivable_vaf`.
4. Evaluator emits only `normal_median_vaf` —
   `test_swap_check_isolation_emits_only_normal_median_vaf`.
5. Gzip supported — `test_swap_check_gzip_supported`.
6. Wired into `run_qc` for a somatic run; never changes exit code —
   `test_discover_qc_includes_swap_check_and_stays_warn_capped`; full suite
   green with no regression.
7. Band boundary (0.30 pass, just above warn) —
   `test_swap_check_band_boundary`.

All satisfied.

## Notes / deviations from plan

- No deviations. The plan's "acceptable simpler alternative" (a `_read_normal`
  clone of `_read_somatic`, rather than extracting a shared
  `_read_column_vafs(vcf_path, resolve_index)`) was used for Phase 2 GREEN,
  and no REFACTOR-phase DRY pass was applied afterward — the plan flags this
  as optional and explicitly says not to touch `_read_somatic`'s shipped
  behavior. Both readers remain independent, small, and covered by their own
  tests.
- Phase 4 (CHANGELOG.md, CAPABILITY_ROADMAP.md, FEATURES.md) was
  intentionally NOT touched, per the task instructions.
