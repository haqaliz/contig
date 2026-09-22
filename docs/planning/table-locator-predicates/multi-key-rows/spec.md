# Spec: multi-key-rows — widen the table locator's row object to multi-key AND-equality

Aspect of `table-locator-predicates` (see `../prd.md`).

## Problem slice

The `TableLocator` row object is validated to exactly-one key
(`reproduce.py:748-752`) and resolved with single-key equality
(`reproduce.py:318-340`). This aspect widens both sites to one-or-more keys
with AND semantics, keeping every other contract identical.

## In-scope requirements (from PRD must/should)

1. `load_claims`: accept `len(raw_row) >= 1`; empty object refused; widened
   message "expected one or more keys"; key/value type guards unchanged.
2. `resolve_cell`: AND of exact `.strip()`ed string equalities across all keys;
   0 or >1 rows → `(None, "row {row!r} matched N rows")`; absent column /
   duplicate header name → unresolved as today; headerless + dict row refused
   as today.
3. Never-raises for all inputs; the wild-input test reworks multi-key from
   invalid to valid shape.
4. Tests: flip `test_load_claims_rejects_row_multi_key_object` to accept;
   add pure resolve tests (hit, 0 rows, 2 rows, absent column, duplicate
   header, ragged row, mixed with int row); add an engine-level
   `run_reproduction` multi-key test (reproduced) and an ambiguity test
   (unverified naming the count).
5. Help text: `contig reproduce` `--claims` table example mentions multi-key
   rows (optional, low risk).

## Out-of-scope boundaries

Numeric coercion, comparison/regex predicates, column ranges, inference-side
widening, notebook locator, freshness guard, `classify`, DIVERGED semantics,
reproduce-guard baseline/scenario changes.

## Acceptance criteria (testable)

- A multi-key claim on a fixture table resolves the exact cell →
  `reproduced`/`within_tolerance` end-to-end through `run_reproduction`.
- A multi-key predicate matching 0 rows → `unverified`, reason contains
  "0 rows"; >1 rows → `unverified`, reason contains the count.
- Single-key claims (incl. frozen `table-locator` scenario) still load and
  resolve identically; `reproduce-guard` passes with the committed baseline.
- `test_load_claims_rejects_row_empty_object` and the key/value-type refusals
  still pass.
- Full suite green: `uv run pytest` (baseline 3209 passed / 1 skipped).

## Dependencies and sequencing

Single aspect, single task sequence: (1) load_claims validation + its tests,
(2) resolve_cell matching + its tests, (3) engine-level end-to-end tests,
(4) help text. No other aspect depends on this one.

## Open questions / risks

None beyond the PRD's: ambiguity degrades to UNVERIFIED by design; the
non-string-key guard stays defensive (JSON keys are always str).