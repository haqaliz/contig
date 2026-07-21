# Phase 2 report — pure gzip-aware TSV/CSV cell reader + resolver (C8 slice 3)

**Scope:** Phase 2 only — `_read_table` + `resolve_cell` in
`src/contig/verification/reproduce.py`, plus a new pure-reader test file.
`run_reproduction`, the CLI, and `load_claims` were NOT touched (verified by
`git status`/`git diff` before commit — only `reproduce.py` and the new test
file are staged).

## Functions added (`src/contig/verification/reproduce.py`)

- `_read_table(path: Path, delimiter: str) -> list[list[str]] | None` —
  opens `.gz`-suffixed paths via `gzip.open(path, "rt", encoding="utf-8",
  newline="")`, everything else via plain `open(..., newline="")`, reads
  with `csv.reader(f, delimiter=delimiter)`, returns `list(reader)`. The
  whole body is wrapped in `try/except (OSError, UnicodeDecodeError,
  csv.Error)` → `None`. Never raises.
- `resolve_cell(rows, column, row, header) -> tuple[str | None, str]` —
  pure, index-safe cell resolver, styled after `resolve_pointer` (never
  raises; any bad step returns `(None, reason)`).
  - Header mode (`header=True`): column resolves by header-name string
    (duplicate name → `None`; absent → `None`) or by 0-based int index (OOR
    → `None`); row resolves by 0-based index over **data rows** (OOR →
    `None`, message names the data-row count) or by a single-key
    `{col: val}` match compared exactly on `.strip()`ed cell strings (0 or
    >1 matches → `None`, message names the match count).
  - Headerless mode (`header=False`): both `column` and `row` must be
    non-bool ints; `row` indexes over ALL rows.
  - A ragged row shorter than the resolved column index, an empty table, or
    a header-only (0 data-row) table all degrade to `(None, reason)` via a
    single final bounds check (`col_idx < 0 or col_idx >= len(target_row)`)
    — no `IndexError` path exists.
  - Every non-conforming `column`/`row` shape (float, `None`, list, bool,
    multi-key dict, non-string dict key/value) falls through to an explicit
    "invalid …" `None` branch rather than being indexed blindly.

Both functions are placed right after `_resolve_delimiter` (Phase 1), before
the `Claim` dataclass, per the plan's function map. Imports added: `csv`,
`gzip` (both stdlib, top of file next to the existing `json`/`math`/`re`
imports).

## Test file: `tests/test_reproduce_tsv_locator.py` (new, 25 tests)

Mirrors `tests/test_reproduce_locator.py`'s structure (module docstring,
happy-path section, failure-path section, never-raises fuzz test).

- Header mode happy paths (4): column-by-name hit, column-by-int hit,
  row-by-index hit, row-by-key single match.
- Header mode failures (9): row-key 0 matches (message names "0 rows"),
  row-key >1 matches (message names "2 rows"), column name absent,
  duplicate header name, column-int OOR, row-int OOR (message names the
  2-data-row count), ragged row shorter than the addressed column, empty
  `rows`, header-only (0 data rows).
- Headerless mode (3): int/int hit, row OOR, column OOR.
- Key-compare semantics (2): trailing-space cell still matches after
  `.strip()`; a genuinely different string does not match (0-match path).
- Fuzz test (1): `test_resolve_cell_never_raises_on_wild_inputs` — a
  ragged 3-row fixture crossed against 10 wild `column` values (str/int/
  float/bool/None/empty-string/negative/OOR) × 13 wild `row` values
  (int/dict variants incl. empty dict, 2-key dict, non-str key/value,
  `None`, list, plain string) × both `header` values, plus 4 degenerate
  table shapes (`[]`, `[[]]`, `[["a"]]`, `[["a","b"],[]]`) crossed against
  representative column/row/header combinations — every call asserts a
  well-shaped `(str | None, str)` tuple comes back, i.e. no exception
  propagates.
- `_read_table` (6): reads a `.tsv` fixture (tab), a `.csv` fixture
  (comma), a stdlib-`gzip`-written `.tsv.gz` fixture; a directory path →
  `None`; a non-UTF-8 file (raw `0xff 0xfe` bytes) → `None`; a missing file
  → `None`.

All new tests were RED first — running the suite before the implementation
existed failed collection with `ImportError: cannot import name
'_read_table' from 'contig.verification.reproduce'`. After implementing
both functions, all 25 pass with no changes needed to the tests.

## Test results

- New file alone: `uv run pytest tests/test_reproduce_tsv_locator.py -q` →
  25 passed, 0 failed (confirmed via `--junit-xml`; this repo's pytest
  9.1.1 install doesn't print the classic terminal summary line for this
  suite size — a pre-existing local quirk unrelated to this change — so
  pass/fail counts were verified via `--junit-xml` output instead of the
  `-q` tail).
- Full suite: `uv run pytest -q --junit-xml=...` → baseline was 1781 tests
  total (1780 passed, 1 skipped). After Phase 2: **1806 tests total, 0
  errors, 0 failures, 1 skipped** (1805 passed) — exactly baseline + 25 new
  tests, 0 regressions.

## Concerns

- None blocking. `run_reproduction`, the CLI, and `load_claims` are
  untouched, confirmed via `git diff --stat` before staging (only
  `src/contig/verification/reproduce.py` and the new test file changed).
- Two pre-existing, unrelated dirty files in the working tree
  (`docs/planning/_card/issue.md`, `docs/planning/_card/understanding.md`)
  and one untracked directory (`docs/planning/reproduce-tsv-csv-locator/`,
  which holds this PRD/plan and did not appear to be committed even after
  Phase 1) were left alone — not staged, not part of this commit.
- `resolve_cell`'s messages are functional but not yet tuned to the exact
  S1 wording examples in the PRD (e.g. `row {gene_id: X} matched 0 rows`);
  message polish is explicitly Phase 5 scope, not Phase 2.
