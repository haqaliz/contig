# Task 1 Report — Phase 1: RNASEQ_PLAUSIBILITY_PACK

Date: 2026-06-28 · Branch: `feat/rnaseq-plausibility/aliz`

## Status

DONE

## Commit

SHA: `2ef3383`
Message: `feat(verify): add WARN-capped RNASEQ_PLAUSIBILITY_PACK (C3 rnaseq slice)`

## Files changed

| File | Change |
|------|--------|
| `src/contig/verification/rule_pack.py` | Added `RNASEQ_PLAUSIBILITY_PACK` (22 lines, WARN-only, not registered in `_RULE_PACKS`) |
| `tests/verification/test_rule_pack.py` | Added 10 new tests for the plausibility pack |

## What was added

`RNASEQ_PLAUSIBILITY_PACK` in `src/contig/verification/rule_pack.py`, placed before `_RULE_PACKS` (not registered in it). Two WARN-capped rules:

- `duplication_rate` / `percent_duplication` / `warn_above: 80.0` — Picard MarkDuplicates slug (unverified), lenient band for RNA-seq.
- `rrna_contamination` / `percent_rRNA` / `warn_above: 10.0` — featureCounts rRNA biotype slug (unverified), high value signals poor rRNA depletion.

Neither rule carries `fail_below` or `fail_above`. The WARN-cap guarantee is enforced by test.

## Tests added

All in `tests/verification/test_rule_pack.py`:

1. `test_rnaseq_plausibility_pack_is_importable` — pack exists and is non-empty
2. `test_rnaseq_plausibility_pack_covers_duplication_and_rrna` — both check names present
3. `test_rnaseq_plausibility_pack_rules_have_warn_above` — each rule has `warn_above`
4. `test_rnaseq_plausibility_pack_rules_have_no_fail_keys` — no `fail_below`/`fail_above`
5. `test_rnaseq_plausibility_duplication_below_band_is_pass` — 30.0 → "pass"
6. `test_rnaseq_plausibility_duplication_above_band_is_warn` — 95.0 → "warn"
7. `test_rnaseq_plausibility_duplication_never_fails` — 99999.0 → not "fail"
8. `test_rnaseq_plausibility_rrna_below_band_is_pass` — 5.0 → "pass"
9. `test_rnaseq_plausibility_rrna_above_band_is_warn` — 50.0 → "warn"
10. `test_rnaseq_plausibility_rrna_never_fails` — 99999.0 → not "fail"

## Test command and output

```
uv run pytest tests/verification/test_rule_pack.py -q
# 59 passed in <1s

uv run pytest -q
# 816 passed, 1 skipped in 10.16s
```

Baseline at branch point: 807 total (806 passed, 1 skipped). After Phase 1: 817 total (816 passed, 1 skipped). +10 tests, all green.

## TDD sequence

- **RED**: 10 tests added first; all failed with `ImportError: cannot import name 'RNASEQ_PLAUSIBILITY_PACK'`.
- **GREEN**: Pack added to `rule_pack.py`; all 10 tests pass, full suite green.
- **REFACTOR**: None required (plan-specified, pack is pure data).

## Notes

- `_status_for` is called directly by name in tests (private but importable); this mirrors the existing test pattern for similar checks.
- Metric slugs (`percent_duplication`, `percent_rRNA`) are best-effort. The UNVERIFIED-when-absent path (Phase 2) absorbs any wrong or missing slug.
- Pack is intentionally not in `_RULE_PACKS`; it will be consumed only by `evaluate_rnaseq_plausibility` (Phase 2).
