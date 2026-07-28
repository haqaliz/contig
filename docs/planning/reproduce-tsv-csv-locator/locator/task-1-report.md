# Task 1 report — Phase 1: schema & validation (`TableLocator` + `load_claims`)

Date: 2026-07-21 · Feature: `reproduce-tsv-csv-locator` (C8 slice 3) · Phase: 1 of 5
(schema & validation only — no reader, no engine, no CLI).

## What was added

`src/contig/verification/reproduce.py`:

- **`TableLocator`** (new frozen dataclass, sits right after `Locator`): `source: str`,
  `column: str | int`, `row: int | dict[str, str]`, `delimiter: str`, `header: bool`. The
  existing JSON `Locator` dataclass is untouched.
- **`Claim.locator`** widened from `Locator | None` to `Locator | TableLocator | None`
  (docstring updated to describe both carriers).
- **`_resolve_delimiter(source, explicit) -> str | None`** (new pure helper, module level,
  placed between `TableLocator` and `Claim`): an explicit delimiter always wins; otherwise
  lower-cases `source`, strips one trailing `.gz`, and maps `.tsv`/`.tab` → `"\t"`,
  `.csv` → `","`; an unrecognized extension with no explicit override returns `None`
  (the caller turns that into a `ClaimsError`). Note: I deliberately gave the explicit
  delimiter precedence over extension inference (not "map extension first, else explicit"
  as the plan's helper pseudocode literally reads) because PRD M3 states "an explicit
  delimiter overrides for any extension" and the plan's own Phase-1 RED bullet 4
  ("explicit `"delimiter": ";"` overrides extension") requires it for a `.tsv` source —
  the literal pseudocode order would have failed that test. Flagging this as an
  intentional resolution of an internal inconsistency between the plan's prose and its
  own test list, in favor of the PRD (authoritative) and the RED list (also authoritative,
  same document).
- **`load_claims`** validation block rewritten (the old `has_from != has_path` two-field
  check generalized): computes `has_from`/`has_path`/`has_column`/`has_row`/
  `has_delimiter`/`has_header`; enforces "`from` must carry exactly one of `{path}` xor
  `{column+row}`"; validates `column` (non-empty str requiring `header:true`, or
  non-negative int), `row` (non-negative int, or a single-key `{str: str}` object
  requiring `header:true`), `delimiter` (single-char string when present), `header`
  (bool, default `True`); resolves the concrete delimiter via `_resolve_delimiter` and
  raises on `None`; builds and attaches a `TableLocator`. The pre-existing JSON `path`
  branch is otherwise byte-identical in behavior (same error triggers, same
  `Locator(source=..., path=...)` construction).

## Tests

`tests/test_reproduce.py`: added `TableLocator` to the import list; added 23 new tests in
a new `# load_claims() -- table locator (...) [C8 slice 3, Phase 1]` cluster, inserted
after the existing JSON-locator cluster and before `run_reproduction()`:

Positive (6):
- `test_load_claims_table_locator_named_tsv_defaults_header_and_delimiter`
- `test_load_claims_table_locator_named_csv_defaults_header_and_delimiter`
- `test_load_claims_table_locator_positional_headerless`
- `test_load_claims_table_locator_infers_delimiter_from_tsv_gz`
- `test_load_claims_table_locator_infers_delimiter_from_csv_gz`
- `test_load_claims_table_locator_explicit_delimiter_overrides_extension`

Reject / `ClaimsError` (17):
- `test_load_claims_rejects_path_and_table_fields_together`
- `test_load_claims_rejects_column_without_row`
- `test_load_claims_rejects_row_without_column`
- `test_load_claims_rejects_column_float`
- `test_load_claims_rejects_column_empty_string`
- `test_load_claims_rejects_column_negative_int`
- `test_load_claims_rejects_row_negative_int`
- `test_load_claims_rejects_row_empty_object`
- `test_load_claims_rejects_row_multi_key_object`
- `test_load_claims_rejects_row_object_empty_key`
- `test_load_claims_rejects_row_object_non_string_value`
- `test_load_claims_rejects_delimiter_not_single_char`
- `test_load_claims_rejects_header_not_bool`
- `test_load_claims_rejects_table_fields_without_from`
- `test_load_claims_rejects_row_object_with_header_false`
- `test_load_claims_rejects_column_str_with_header_false`
- `test_load_claims_rejects_unknown_extension_without_delimiter`

All existing tests in the file (including the JSON-locator and flat-claim clusters) were
left unmodified and still pass unchanged.

Note on "row object with non-string key": JSON object keys are always strings after
`json.loads`, so a literal non-string key is unrepresentable via a claims-file fixture. I
covered the reachable analogue instead — an object with an **empty-string** key
(`{"": "X"}`, which violates the PRD's "col a non-empty string" requirement) — via
`test_load_claims_rejects_row_object_empty_key`. The implementation still defensively
checks `isinstance(row_key, str)` (dead code under real JSON input, but harmless and
future-proofs any non-JSON caller).

## RED → GREEN

- RED: `uv run pytest tests/test_reproduce.py -q` failed at collection —
  `ImportError: cannot import name 'TableLocator' from 'contig.verification.reproduce'`
  (confirmed before writing any implementation).
- GREEN: after implementing, `uv run pytest tests/test_reproduce.py` → `74 passed in 0.34s`
  (51 pre-existing + 23 new).
- One style fix during REFACTOR: a `raise ClaimsError(...)` line was 102 chars (file's de
  facto convention keeps lines ≤ ~100); wrapped it to a multi-line call, matching the
  surrounding style. Re-ran full suite after the wrap — still green.

## Final full-suite run

```
uv run pytest
...
1780 passed, 1 skipped in 12.73s
```

Baseline was 1757 passed, 1 skipped; this phase added 23 tests (1757 + 23 = 1780), 0
failures, 0 regressions.

## Scope discipline

Did not touch `_read_table`, `resolve_cell`, `_observe_table_located`, the
`run_reproduction` dispatch, or `cli.py` — those are Phases 2–4. Stdlib only, no new
dependency, no `models.py` change. `git status` shows unrelated pre-existing modifications
(`docs/planning/_card/issue.md`, `docs/planning/_card/understanding.md`, `uv.lock`) that
predate this task and were left untouched and unstaged.

## Concerns

- The `_resolve_delimiter` precedence resolution (explicit-always-wins) described above is
  the one place I diverged from the plan document's literal helper pseudocode. I'm
  confident it's correct (PRD M3 + the plan's own RED bullet 4 both require it), but
  flagging it explicitly since a literal reading of the "Project setup" bullet's pseudocode
  would disagree.
- None of the enumerated RED-list bullets were skipped; coverage looks complete against
  the plan's Phase 1 bullet 5 list.
