# Phase 3 report — engine dispatch for TSV/CSV table locators (C8 slice 3)

**Scope:** Phase 3 only — `_observe_table_located` + a `_table_cache` + the
isinstance dispatch inside `run_reproduction`, in
`src/contig/verification/reproduce.py`, plus extending
`tests/test_reproduce.py`. The CLI (`cli.py`), `load_claims`,
`resolve_cell`/`_read_table` bodies were NOT touched (verified by `git diff`
before commit — only `reproduce.py` and `tests/test_reproduce.py` are
staged; pre-existing unrelated dirty files — `docs/planning/_card/*.md`,
`uv.lock` — were left alone).

## Changes (`src/contig/verification/reproduce.py`)

- `_table_cache: dict[str, list[list[str]] | None]` — a per-`run_reproduction`-call
  cache keyed by resolved absolute path, mirroring `_json_cache`.
- `_observe_table_located(loc: TableLocator) -> tuple[float | None, str]` —
  sibling of `_observe_located`, defined right after it:
  - same containment guard: `(repo_path / loc.source).resolve()` then
    `resolved.relative_to(repo_root)`; a `ValueError` (escape) returns
    `(None, "…escapes the repo")` **before any read** — `_table_cache`/`_read_table`
    are never touched on this path.
  - populates `_table_cache` via `_read_table(resolved, loc.delimiter)` once
    per resolved path; a `None` read (missing/dir/non-utf8/unparseable) →
    `(None, "…is missing or unreadable")`.
  - calls `resolve_cell(rows, loc.column, loc.row, loc.header)`; a `None`
    cell → `(None, "…did not resolve: {reason}")` (never `diverged`).
  - parses the cell string with `float(cell)` in `try/except ValueError` →
    `(None, "…is not a finite number")`; a parsed `nan`/`inf` →
    `(None, "…is not finite: …")`. Otherwise `(value, "")`. This is the
    deliberate divergence from the JSON reader: a numeric-looking cell
    string is the *normal* case for a table, so it classifies instead of
    going UNVERIFIED.
- Dispatch in the per-claim loop: `if isinstance(claim.locator, TableLocator): observed, fail_msg = _observe_table_located(claim.locator)` else the
  unchanged `_observe_located(claim.locator)` call — both feed the exact
  same unverified/`classify` plumbing that already existed for JSON locators
  (no duplicated branch logic beyond the dispatch itself).

No changes to `Locator`/`TableLocator`/`load_claims`/`resolve_cell`/`_read_table`.

## Tests added (`tests/test_reproduce.py`)

New cluster after the existing JSON-located-claim tests (16 new tests),
using on-disk `tmp_path` `.tsv`/`.csv` fixtures and the existing `_run`/`_noop_executor`/`_fake_executor`/`_write_located` helpers:

- named `{gene_id: X}` key-match claim → `reproduced`; drifted → `diverged`
  (message names both values); near → `within_tolerance`.
- positional/headerless claim (`header=False`, int column+row) → resolves.
- missing file, unresolved column name, row-key 0-match, row-key >1-match,
  a ragged row (header has 3 cols, data row has 1), an unparseable cell
  (`"NA"`), a non-finite cell (`"inf"`) → all `unverified`, never `diverged`;
  assertions check the message names the specific reason where the plan
  calls for it (`"nonexistent_col"`, `"0 rows"`, `"2 rows"`).
- `test_run_reproduction_table_claim_numeric_string_cell_is_the_observed_value`
  — a `"30.4"` cell classifies as `reproduced`, explicitly asserting the
  documented divergence from the JSON locator's numeric-string-is-UNVERIFIED
  rule.
- `test_run_reproduction_table_claim_same_file_parsed_once` — two claims
  target different cells of the same `.tsv`; a `monkeypatch`-installed
  counting wrapper around `reproduce_module._read_table` asserts exactly one
  call.
- `test_run_reproduction_mixed_table_and_json_and_flat_claims_resolve_independently`
  — a table claim, a JSON-locator claim, and a flat `--results`-map claim in
  one run all resolve to `reproduced` independently.
- `test_run_reproduction_table_claim_escaping_repo_is_unverified_and_not_read`
  — a real, readable `../outside_table_secret/secret.tsv` (whose value WOULD
  reproduce if read) → `unverified`, message contains `"escapes the repo"`,
  and the same counting-`_read_table` spy asserts **zero** calls, proving
  the file is never opened.
- `test_run_reproduction_table_claim_nonzero_exit_is_unverified` — a
  nonzero-exit run marks a table-located claim unverified via the existing
  short-circuit (unchanged behavior, exercised for the new locator type).

## Verification

- `uv run pytest tests/test_reproduce.py -q` — green (98 tests in file).
- `uv run pytest` (full suite) — **1821 passed, 1 skipped**, 0 failures
  (baseline after Phase 2 was 1805 passed, 1 skipped + 16 new tests = 1821,
  exact match).
- RED confirmed before implementing: 10 of the 16 new tests failed pre-GREEN
  (the other 6 happened to already read `unverified` through the old
  fallback path — e.g. the table file fails JSON-parsing when read as JSON —
  so they weren't discriminating on their own, but all 16 now exercise the
  real table-locator code path post-GREEN).

## Commit

`b5f840c` — `feat(reproduce): route TSV/CSV table locators through
run_reproduction (C8 slice 3)`

## Blocking concerns

None. Phase 4 (CLI containment loop widening + end-to-end tests) is next,
per the plan — not touched here.
