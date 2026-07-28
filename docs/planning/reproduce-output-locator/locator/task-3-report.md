# Task 3 report — Phase 3: Located value-binding in `run_reproduction`

**Slug:** `reproduce-output-locator` · **Aspect:** `locator` · **Phase:** 3 of 4
**Branch:** `feat/reproduce-output-locator/aliz` · **Commit:** `975c74a`

## What changed

`src/contig/verification/reproduce.py`, inside `run_reproduction`:

- `:263-311` — new inner helper `_observe_located(loc: Locator) -> tuple[float | None, str]`
  (added right before the existing `exit_code = executor(...)` call, `:312`). Resolves
  `repo_path / loc.source`, guards containment via `.resolve().relative_to(repo_root)` in a
  `try/except ValueError` (an escape returns `(None, "...escapes the repo")` and never reads the
  file), caches parsed JSON per resolved path in `_json_cache` for the duration of the call,
  disambiguates "missing" vs. "unparseable" via `resolved.exists()`, resolves `loc.path` with the
  Phase-1 `resolve_pointer`, and rejects `None` (unresolved path), `bool`, non-`(int, float)`
  (including numeric strings — strict, no coercion), and non-finite (`NaN`/`inf`) targets, each
  with its own message. On success returns `(float(target), "")`.
- `:349-378` — the per-claim loop now branches: `if claim.locator is not None:` calls
  `_observe_located`, maps `observed is None` to a `ClaimResult(status="unverified", observed=None,
  message=fail_msg)`, otherwise calls the unchanged `classify(claim.value, observed,
  claim.tolerance)` and appends the result, then `continue`s past the existing flat-`results`
  branch. Locator-less claims fall through to the original flat-`results` code unchanged (byte-
  identical, not touched).

No changes to `classify`, `ClaimResult`, `ReproduceRecord`, or the flat-`results` branch. No new
runtime deps (`pyproject.toml` untouched).

## New tests (`tests/test_reproduce.py`, appended after the existing `run_reproduction` group)

Helpers added: `_run(tmp_path, claims, executor, **overrides)`, `_write_located(tmp_path, rel,
payload)`, `_noop_executor(exit_code=0)` — mirror the existing `_fake_executor` closure pattern.

- `test_run_reproduction_located_claim_matching_is_reproduced`
- `test_run_reproduction_located_claim_drifted_is_diverged_with_message`
- `test_run_reproduction_located_claim_near_value_is_within_tolerance`
- `test_run_reproduction_located_claim_missing_file_is_unverified`
- `test_run_reproduction_located_claim_unparseable_json_is_unverified`
- `test_run_reproduction_located_claim_unresolved_path_is_unverified`
- `test_run_reproduction_located_claim_string_target_is_unverified_strict`
- `test_run_reproduction_located_claim_numeric_string_target_is_unverified_strict`
- `test_run_reproduction_located_claim_boolean_target_is_unverified`
- `test_run_reproduction_located_claim_nan_target_is_unverified`
- `test_run_reproduction_located_claim_inf_target_is_unverified`
- `test_run_reproduction_mixed_located_and_flat_claims_resolve_independently`
- `test_run_reproduction_located_claim_escaping_repo_is_unverified_and_not_read` (writes a real
  file at `tmp_path.parent / "outside_secret/secret.json"` with a value that WOULD reproduce if
  read, points a claim's `from` at it via `../outside_secret/secret.json`, asserts `unverified`,
  `observed is None`, and `"escapes the repo"` in the message)
- `test_run_reproduction_located_claim_nonzero_exit_is_unverified`

RED confirmed before the GREEN implementation: 5 of the 14 new tests failed (the 3 classify-path
tests, the mixed test, and the escape test — the rest incidentally passed already because
locator-less-branch lookups on a missing/wrong flat key already produce `unverified`/`observed is
None`, just with a different message than the located-specific ones assert).

## Validation

```
uv run pytest tests/test_reproduce.py -q
```
```
..................................................                       [100%]
```
(50 tests, all pass)

```
uv run pytest tests/test_reproduce_locator.py tests/test_cli_reproduce.py \
              tests/test_reproduce_models.py tests/test_reproduce_bundle.py -q
```
```
.................................................                        [100%]
```
(all pass)

```
uv run pytest -q
```
Full suite: all dots/`s` (one skip, pre-existing and unrelated), zero `F`/`E` markers across the
run — no regressions.

## Concerns

- Two unrelated files (`docs/planning/_card/issue.md`, `docs/planning/_card/understanding.md`)
  were already modified in the worktree before this task started (not by this task, not touched,
  not committed here) — flagging in case they need separate attention.
- This worktree's `pytest -q` does not print the usual final `N passed` summary line (output ends
  at the last dot row); verified pass/fail state via absence of `F`/`E` markers instead. Cosmetic,
  not a functional issue.
- Phase 4 (CLI containment pre-check, `--results` help text) is explicitly out of scope for this
  task and was not started.

## Review fixes (I1/I2)

A whole-branch review found two Important defects that broke the binding invariant "the
walker/observer NEVER raises; every resolution failure → UNVERIFIED." Both fixed TDD (RED
confirmed before GREEN), commit `cec03cc`.

**I1 — unicode-digit index raised in `_parse_path`.**
`src/contig/verification/reproduce.py:51` guarded a `[n]` index with `inner.isdigit()`, which is
broader than what `int()` accepts (e.g. `"²".isdigit()` is `True` but `int("²")` raises
`ValueError`), so `resolve_pointer(..., "a[²]")` crashed instead of returning `None`. Fixed by
changing the guard to `inner.isdecimal()` (`reproduce.py:51-54`), which aligns exactly with what
`int()` parses — Arabic-Indic and other true decimal digits (e.g. `"a[٠]"` → index 0) still work.

- New test: `tests/test_reproduce_locator.py::test_resolve_pointer_unicode_digit_index_returns_none_not_raise`
  (RED: raised `ValueError: invalid literal for int() with base 10: '²'` before the fix; GREEN
  after).
- New test: `tests/test_reproduce_locator.py::test_resolve_pointer_arabic_indic_decimal_index_works`
  (asserts `"a[٠]"` still resolves to index 0 — passed before and after, included as a companion
  check on the tightened guard).

**I2 — non-UTF-8 `from` file raised in `_observe_located`.**
`src/contig/verification/reproduce.py:284-286` read the locator file via
`json.loads(resolved.read_text())` under `except (json.JSONDecodeError, OSError)`. A non-UTF-8
file makes `read_text()` raise `UnicodeDecodeError`, a `ValueError` subclass (not `OSError`), so it
propagated uncaught and crashed the run. Fixed by broadening the except clause to
`except (ValueError, OSError)` (`reproduce.py:284-289`), which still covers
`json.JSONDecodeError` (already a `ValueError` subclass) and now also `UnicodeDecodeError`. The
existing `resolved.exists()` check keeps "missing" vs. "not valid JSON" message disambiguation
intact.

- New test: `tests/test_reproduce.py::test_run_reproduction_located_claim_non_utf8_file_is_unverified_not_raise`
  (writes `out/summary.json` as `b"\xff\xfe\x00bad"`; RED: raised
  `UnicodeDecodeError: 'utf-8' codec can't decode byte 0xff in position 0: invalid start byte`
  before the fix; GREEN after — asserts `status == "unverified"`, `observed is None`, and
  `"not valid JSON"` in the message).

### Validation

```
uv run pytest tests/test_reproduce_locator.py tests/test_reproduce.py -q
```
```
........................................................................ [100%]
```
(no summary line printed under `-q` in this worktree, as noted above; re-ran without `-q` to
confirm the count: `72 passed in 0.10s`)

```
uv run pytest
```
```
1730 passed, 1 skipped in 12.85s
```

No other behavior changed; CLI, models, and `classify` untouched. All pre-existing tests stay
green.
