# Task 2 report — `RNASEQ_COMPOSITION_PACK` rule pack (Phase 2)

Branch: `feat/rnaseq-mapping-composition-plausibility/aliz`
Plan: `docs/planning/rnaseq-mapping-composition-plausibility/composition-checks/plan_20260711.md`, Phase 2.

## What was added

### `src/contig/verification/rule_pack.py`

Added `RNASEQ_COMPOSITION_PACK: list[dict]` immediately after `ANNOTATION_PLAUSIBILITY_PACK`
(and before the `X_HET_LOW`/sex-plausibility constants), verbatim per the plan's Phase 2
GREEN block:

- Leading comment: fractions are in `[0,1]` (not the 0–100 percent scale used by the other
  MultiQC-sourced packs); WARN-capped, uncalibrated engineering defaults; evaluated by the
  dedicated `read_distribution` gate in `runner._discover_qc`; deliberately **not**
  registered in `_RULE_PACKS`.
- Three rules, each carrying only a warn bound (no `fail_below`/`fail_above`):
  - `exonic_fraction` — `warn_below: 0.50`
  - `intronic_fraction` — `warn_above: 0.30`
  - `unassigned_fraction` — `warn_above: 0.30`
- Messages copied verbatim from the plan.

`RNASEQ_COMPOSITION_PACK` is **not** added to `_RULE_PACKS` (mirrors
`RNASEQ_PLAUSIBILITY_PACK`, `SOMATIC_PLAUSIBILITY_PACK`, `ANNOTATION_PLAUSIBILITY_PACK`).
No other pack, `evaluate()`, or `_status_for()` was touched. `runner.py` and
`rnaseq_metrics.py` were not touched (out of scope for this task).

### `tests/verification/test_rule_pack.py`

Extended with a new `# --- RNA-seq read-composition plausibility pack (C3 slice, Phase 2) ---`
section (after the existing `RNASEQ_PLAUSIBILITY_PACK` tests), mirroring the house style used
for the other plausibility packs (local import inside each test, `_status_for`/`evaluate`
driven directly). 9 new tests:

1. `test_rnaseq_composition_pack_has_exactly_three_rules` — `len(...) == 3`.
2. `test_rnaseq_composition_pack_covers_exonic_intronic_unassigned` — metric-slug set is
   exactly `{exonic_fraction, intronic_fraction, unassigned_fraction}`.
3. `test_rnaseq_composition_pack_rules_have_no_fail_keys` — WARN-cap guarantee, no
   `fail_below`/`fail_above` on any rule.
4. `test_rnaseq_composition_pack_is_not_registered_in_rule_packs` — the pack object is not
   one of `_RULE_PACKS.values()`.
5. `test_healthy_composition_sample_passes_every_check` — the plan's healthy-yeast-shaped
   fraction dict (`exonic≈0.9998, intronic≈0.0002, unassigned≈0.112`) driven through
   `evaluate()` yields 3 pass results.
6. `test_low_exonic_fraction_warns_never_fails` — exonic below 0.50 → warn.
7. `test_high_intronic_fraction_warns_never_fails` — intronic above 0.30 → warn.
8. `test_high_unassigned_fraction_warns_never_fails` — unassigned above 0.30 → warn.
9. `test_rnaseq_composition_extreme_values_never_fail` — worst-case values on all three
   metrics (`0.0`/`1.0`/`1.0`) driven through the shared `evaluate()` scorer still never
   produce `"fail"`.

## Validation

```
uv run pytest tests/verification/test_rule_pack.py -q
```
→ `72 passed in 0.07s` (63 pre-existing + 9 new).

```
uv run pytest -v
```
→ `1472 passed, 1 skipped in 11.85s` (baseline on this branch was 1463 passed, 1 skipped;
+9 new tests, 0 broken).

Note: `uv run pytest -q` (the exact command given in the task) runs clean with exit code 0
but its terminal-summary line ("N passed...") is not emitted to stdout in this environment
under `-q` for the full-suite run (a pytest 9.1.1 progress-bar rendering quirk observed when
stdout isn't a real tty, reproduced even via a plain Python subprocess capture) — the dotted
progress output and exit code 0 are present, and `-v` reliably prints the summary line, which
is what was used to get the exact pass count above. This is a display artifact of this run,
not a test failure; not investigated further since it's outside this task's scope.

## Concerns

None regarding scope or correctness. One minor environmental observation only: see the
`uv run pytest -q` summary-line note above — worth a quick look if it recurs for later
phases' validation runs, but it did not affect pass/fail counts (`-v` and exit codes confirm
the suite is green).
