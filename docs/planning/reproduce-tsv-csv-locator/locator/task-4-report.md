# Phase 4 report — CLI containment + end-to-end (C8 slice 3)

Date: 2026-07-21 · Aspect: `locator` · Phase 4 of 5.

## Scope

Phase 4 only: `cli.py` containment pre-check for table locators + S2 help
note + end-to-end/containment tests in `tests/test_cli_reproduce.py`. No
`run_reproduction`, `load_claims`, or reader changes (none made).

## Finding: the containment loop already covered `TableLocator`

Read `src/contig/cli.py:800-816` (the `from`-containment loop) before writing
any test. The loop is:

```python
for claim in claims_list:
    if claim.locator is None:
        continue
    resolved_locator = (repo_path / claim.locator.source).resolve()
    try:
        resolved_locator.relative_to(repo_root)
    except ValueError:
        typer.echo(f"locator 'from' path escapes the repo: {claim.locator.source}", err=True)
        raise typer.Exit(code=1)
```

It is **not** `isinstance`-guarded — it only checks `claim.locator is None`
and then reads `.source` duck-typed. Since `TableLocator.source` exists
(confirmed in `src/contig/verification/reproduce.py`, `TableLocator` frozen
dataclass, field `source: str`), this loop already caught escaping/absolute
table `from` paths with **zero code changes**. I verified this empirically:
wrote the four containment/e2e table tests first and ran them against the
pre-Phase-4 `cli.py` — all four passed immediately (no RED state for those).
So no fix was needed for the loop itself, per the plan's built-in escape
hatch ("if the containment loop can't cleanly read `.source` off both
carriers... " — it could, cleanly, already).

The one genuine RED→GREEN item was **S2** (help note), which had no
pre-existing implementation.

## Changes made

### `src/contig/cli.py`

Extended the `reproduce` command's docstring (used verbatim as the Click/Typer
help text) with a one-line note plus a short example, per PRD S2:

```
A claim's locator may target a JSON value (`from` + `path`, a JSONPath-lite
into a JSON file) or a TSV/CSV cell (`from` + `column` + `row`, optionally
`header`/`delimiter`) -- e.g. `{"id": "log2fc", "value": -2.31, "from":
"out/de.tsv", "column": "log2FoldChange", "row": {"gene_id": "ENSG1"}}`.
```

No other `cli.py` change. The containment loop is untouched (already
correct).

### `tests/test_cli_reproduce.py`

Added 5 tests, mirroring the existing JSON-locator containment/e2e tests
(`:339-425`) and the help-introspection convention from
`test_reproduce_registers_allow_install_flag` (per the repo's standing
lesson: never assert on Rich-rendered `--help` text in a no-TTY CI —
introspect instead):

1. `test_reproduce_escaping_table_locator_from_errors_and_writes_no_record` —
   `from: "../secret.tsv"` with `column`/`row` → exit non-zero, stderr names
   the path, no `reproduce_record.json` written.
2. `test_reproduce_absolute_table_locator_from_errors_and_writes_no_record` —
   `from: "/etc/de.tsv"` → same.
3. `test_reproduce_located_table_claim_end_to_end_reports_verdict` — a fake
   executor writes a real `out/de.tsv` (tab-separated, header + one data row)
   matching a named table claim (`column: "log2FoldChange"`,
   `row: {"gene_id": "ENSG1"}`); asserts `REPRODUCED` in rendered output,
   claim id in output, and a `reproduce_record.json` written under
   `runs_dir`.
4. `test_reproduce_fail_on_diverged_exits_nonzero_for_table_claim` — same
   fixture with a drifted observed value and `--fail-on-diverged`; asserts
   non-zero exit, `DIVERGED` in output, and the bundle is still written
   (the flag only affects exit code, not whether the record is written —
   matches the existing JSON `--fail-on-diverged` contract).
5. `test_reproduce_docstring_notes_table_locator_support` — introspects
   `contig.cli.reproduce.__doc__` directly (not `--help` output) for the S2
   note; the only test that was RED before the `cli.py` docstring edit.

Confirmed RED before the fix: ran
`uv run pytest tests/test_cli_reproduce.py -q -k docstring` against the
pre-edit docstring — failed on `assert "tsv" in doc.lower() or "csv" in
doc.lower()`. After adding the docstring note, it passes.

Confirmed tests 1-4 were already GREEN against the pre-Phase-4 `cli.py` (ran
`-k "table_locator or table_claim"` before any `cli.py` edit — 4 passed, 1
failed [the docstring test]), which is the evidence backing the "loop already
covered it" finding above. They stay in the suite as regression coverage for
Phase 4's scope even though they didn't require new production code.

## Test results

- `uv run pytest tests/test_cli_reproduce.py -q` → 24 passed (was 19 before
  Phase 4; +5 new).
- Full suite: `uv run pytest --tb=no -rN` → **1826 passed, 1 skipped** in
  13.04s (0 failures). Baseline after Phase 3 was 1821 passed, 1 skipped;
  +5 matches the 5 new tests added.

## Concerns

- None blocking. The only notable thing is that 4 of the 5 new tests didn't
  require a production fix — they exist to lock in behavior that was already
  correct by construction (duck-typed `.source` access), per the plan's own
  anticipation of this outcome. Left them in as explicit regression coverage
  for the table-locator path through the CLI, since prior to this phase there
  was no test proving the containment loop handled `TableLocator` — only
  proving it handled `Locator` (JSON).
- Did not touch `run_reproduction`, `load_claims`, or the reader, per scope.
- Did not touch `CHANGELOG.md` or `docs/technical/CAPABILITY_ROADMAP.md` —
  that's Phase 5.
