# Task 1 report — Phase 1: pure path walker `resolve_pointer`

**Slug:** `reproduce-output-locator` · **Aspect:** `locator` · **Slice:** C8 slice 1.5
**Plan:** `docs/planning/reproduce-output-locator/locator/plan_20260718.md` — Phase 1 only
**Branch:** `feat/reproduce-output-locator/aliz` · **Commit:** `9193f56`

## What was added

`src/contig/verification/reproduce.py`, inserted after the module constants
(`_STATUSES`, `_DEFAULT_TOLERANCE`) and before `class ClaimsError`:

- `_parse_path(expr: str) -> list[str | int] | None` — `reproduce.py:28`
  Tokenizer for a dotted+`[n]` path expression. Strips a leading `$` and one
  leading `.`. Returns a list of `str` (dict keys) / `int` (list indices)
  tokens, or `None` on any malformed input (unclosed bracket, non-digit
  index, empty segment, double dot, trailing dot, empty/`$`/`$.` expression,
  trailing garbage after a `]`, etc). Stdlib only, no regex.
- `resolve_pointer(data: object, expr: str) -> object | None` — `reproduce.py:76`
  Walks `data` (nested dict/list from parsed JSON) token by token. Any
  unresolved step (missing key, index out of range, index applied to a
  non-list, key applied to a non-dict) or malformed `expr` returns `None`.
  Never raises. A JSON `null` at the target also returns `None` (the walker
  does not distinguish "missing" from "present but null" — both are
  "unresolved" from the caller's point of view, matching AC2).

No other functions/behavior in the module were touched. Both new functions
sit above `ClaimsError`/`Claim`/`load_claims`, i.e. purely additive at the
top of the file after the existing imports and constants, as the plan
specified.

## Tests

New file: `tests/test_reproduce_locator.py` — 19 tests, all green.

Coverage:
- AC1 happy paths: `$.model.auc` on a nested dict; `samples[0].n` (dict →
  list → dict); top-level list `[0].name`; `$.`/no-prefix/`$` (no dot)
  equivalence for a dict root; bare top-level key with and without prefix.
- AC2 malformed/miss cases (each asserted to return `None`, never raise):
  missing key, index out of range, index-on-dict, key-on-list, `"a..b"`,
  `"a[x]"`, `"a["`, `"a[0]b"`, `"a."`, `""`, `"$"`, `"$."`, and a JSON `null`
  target (via `json.loads` to get an authentic `None` leaf).
- A grab-bag "never raises" test (`test_resolve_pointer_never_raises_on_wild_inputs`)
  running ~16 adversarial expressions against a dict, a list, a string, and
  `None` as the root — 4×16 = 64 additional assertions that `resolve_pointer`
  degrades to `None` rather than raising, for root types beyond the plan's
  minimum AC2 list.

## Commands run and final output

RED (before implementation):
```
uv run pytest tests/test_reproduce_locator.py -q
```
→ `ImportError: cannot import name 'resolve_pointer' from 'contig.verification.reproduce'`
(collection error — confirmed RED as expected, since the file was written
before any implementation existed).

GREEN (after implementation):
```
uv run pytest tests/test_reproduce_locator.py -q
```
→ `...................                                                      [100%]` (19 passed)

Baseline regression check:
```
uv run pytest tests/test_reproduce.py tests/test_cli_reproduce.py tests/test_reproduce_models.py tests/test_reproduce_bundle.py -q
```
→ `..........................................................               [100%]` (60 passed)

Full repo suite:
```
uv run pytest -q
```
→ all passed (1 skipped, everything else green — no regressions).

## Concerns

None. Scope was held strictly to Phase 1: no `Locator` dataclass, no
`Claim`/`load_claims` changes, no `run_reproduction` changes, no CLI changes.
`src/contig/cli.py` was not touched. The only source file modified is
`src/contig/verification/reproduce.py` (purely additive), plus the new test
file.

One implementation note carried over verbatim from the plan's reference
shape: the comment `import re  # only if the impl uses it` in the plan was
not applicable here — the implementation is regex-free per the plan's own
reference parser, and no new imports were added to `reproduce.py`.
