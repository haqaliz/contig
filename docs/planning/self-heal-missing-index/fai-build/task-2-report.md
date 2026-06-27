# Task 2 report — fai-build Phase 2 (wire the build into the loop)

**Date:** 2026-06-27 · **Branch:** `feat/self-heal-missing-index/aliz`
**Status:** DONE

## Summary

Phase 2 wires a missing-`.fai` build into the self-heal loop. When a
`build_index` reference patch is applied (auto-approve, chosen, or single
confirm), the loop now parses the missing `.fai` from the diagnosis, runs the
injected `IndexBuilder` with `samtools faidx <fasta>`, and branches the recorded
outcome honestly:

- success → `built_index_and_retried` (loop retries)
- non-zero build → `index_build_failed` (honest FAIL, no extra retry)
- unparseable path → `index_unresolvable` (honest FAIL, builder never called)

Non-`build_index` gated patches are unchanged (still `approved_and_retried` /
`chose_and_retried`). `apply_patch` itself is untouched — the build is the fix at
the loop level.

## Files changed

- `src/contig/self_heal.py`
  - Hardened `_FAI_TOKEN_RE` to `r"\S+\.fai(?=\s|$|[:,;])"` (token-end boundary so
    `ref.fasta.fai_backup` is not truncated).
  - Imported `IndexBuilder`, `default_index_builder` from `contig.runner`.
  - Added `index_builder: IndexBuilder = default_index_builder` to `self_heal_run`.
  - Added the shared helper `_apply_patch_and_maybe_build(...)` returning
    `(target, params, outcome, detail, continue_)`.
  - Updated the stale `apply_patch` docstring note about `build_index` being
    handled one level up.
  - Rewired the **three** gated apply sites to call the helper, record the
    returned `outcome`+`detail`, and `_finalize(...)` when `continue_` is False.
- `src/contig/cli.py`
  - Imported and passed `index_builder=default_index_builder` into `self_heal_run`
    (mirrors the existing `default_executor` seam so the CLI build is injectable).
- `tests/test_self_heal.py`
  - New AC1–AC4 acceptance tests + two `_parse_missing_fai` boundary unit tests.
  - Updated 3 existing build_index integration tests to inject a fake builder and
    assert the new `built_index_and_retried` outcome (behavior legitimately changed
    for the build path).
- `tests/test_cli.py`
  - `test_run_auto_approve_applies_gated_patch`: monkeypatch
    `contig.cli.default_index_builder` to a fake; assert `built_index_and_retried`.

## The three apply sites touched

1. **auto_approve** site (`if auto_approve:`), default_outcome `approved_and_retried`.
2. **ambiguous-chosen** site (`if chosen is not None:`), default_outcome `chose_and_retried`;
   preserves the surrounding `_write_status(run_dir, "running")`.
3. **unambiguous-approve** site (`if decision == "approve":`), default_outcome
   `approved_and_retried`; preserves `_write_status(run_dir, "running")`.

Each now: helper call → `_record_attempt(... outcome, detail)` → `if not cont:
return _finalize(...)` → else `attempt += 1; continue`.

## How AC4 (unparseable) was driven

Used the real detect path, no monkeypatching: the log `"ERROR: index file not
found"` hits `detect.py`'s `missing_index` rule (line contains both `not found`
and `index`) while carrying **no** `.fai` token, so `_parse_missing_fai` returns
`None`. With `auto_approve=True` the loop reaches the build helper, gets `None`,
and finalizes `index_unresolvable` / `verdict == "fail"` with the builder never
called. This is the simplest reliable trigger and exercises the production
detector rather than a stub.

## Test commands + output

- `uv run pytest tests/test_self_heal.py -q` → all pass.
- `uv run pytest` → **789 passed, 1 skipped** (the 1 skip is the env-gated LLM
  detector test, pre-existing).
- AC6: `test_apply_patch_reference_build_index_is_rerun_only` passes unchanged.

## Concerns

- **Existing tests updated:** three `test_self_heal.py` integration tests and one
  `test_cli.py` test asserted the old `approved_and_retried`/`chose_and_retried`
  outcome on what is now a real build path. They legitimately change to
  `built_index_and_retried` and inject a fake builder; this is the intended
  semantic change, not a regression. No assertion was loosened to hide a failure.
- **CLI seam added (slightly beyond the loop):** `cli.py` now passes
  `index_builder=default_index_builder`. Without it the CLI would shell out to a
  real `samtools` in `run`, breaking the CLI test in CI. The wiring mirrors the
  existing `default_executor` injection pattern, so it is minimal and consistent.
- **ruff not available** in this environment and not declared in `pyproject.toml`,
  so the optional lint step was skipped.
- Builder cwd is `run_dir` (the resolved run directory), per the plan; real-run
  path-mismatch risk (PRD R2) is noted as a follow-up, out of scope here.
