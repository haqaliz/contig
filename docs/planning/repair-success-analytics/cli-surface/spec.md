# Aspect spec — `cli-surface`

The thin half: one Typer command that renders `stats-core`'s dict as text or JSON.

## Problem slice

The numbers are only useful if a reader can tell what they are counting and can discard
what they distrust. This aspect is where "0 recoveries over 15 runs" either reads as
rigour or as breakage.

## In scope

- **`contig repair-stats`** in `src/contig/cli.py`, following `clusters` (`cli.py:3672`)
  and `coverage` (`cli.py:3706`) exactly:
  - `--runs-dir` (`typer.Option("runs", ...)`, matching `cli.py:2717`)
  - `--json` (dumps the pure dict verbatim, as `coverage` does)
  - plain `typer.echo` only — **no Rich tables**; counts as raw ints; keys always
    `sorted()` for determinism.
- **Every total labelled `runs` or `steps`.** No unlabelled number anywhere in the output.
- **The rate names its own denominator** in text mode, and states how many runs were set
  aside as `not_analyzable` or `attendance_unknown`, and why.
- **Thin-data flag** following `corpus.py:279`'s `_THIN_THRESHOLD = 3`, rendered as the
  literal `"  THIN"` suffix (`cli.py:3733`).
- **Legacy disclosure**: when any step is `legacy_derived`, say so and say how many —
  this is the difference between an honest report and an apparently-broken one.
- **A one-line note distinguishing this from `heal-guard`'s `recovery_rate`** (real runs
  vs frozen synthetic scenarios) — PRD R8 makes this a requirement, not a nicety.
- **Empty/missing runs dir** → "no runs", never `0%` (`list_run_ids` returns `[]`,
  `workspace.py:44`).

## Out of scope

- The taxonomy and aggregation (that is `stats-core`).
- A dashboard surface; `--snapshot`/`--history`; changes to `report.py`'s binary
  `_applied_word` (PRD R-Risk-2 accepts the divergence for now).

## Acceptance criteria (testable) — `tests/test_cli_repair_stats.py`

Use `CliRunner()` + `tmp_path`, building real bundles via `write_bundle` (the
`_write_run` idiom at `tests/test_cli.py:132-138`), **not** raw JSONL — this command needs
real `run_record.json` files. Assert exit codes, parsed JSON, and plain-echo substrings.

1. `--json` emits the documented keys and parses; per-family and per-class counts match a
   hand-built fixture.
2. Text mode names the rate's denominator and states the `not_analyzable` count.
3. A fixture containing a legacy step (key omitted on disk) produces output that says
   `legacy`/derived and gives the count — asserted on the rendered text.
4. Missing runs dir → exit code 0 with a "no runs" message, **not** `0%`.
5. A run with an `attendance_unknown` step is reported in its own bucket and named in the
   text output.
6. Determinism: two invocations over the same fixture produce byte-identical output.
7. **No assertion on `--help` output** — there is no such convention in this repo (the
   only `--help` string in `tests/` is an unrelated parametrize value,
   `tests/test_paper_intake.py:64`).

## Dependencies and sequencing

Depends on `stats-core` (the dict shape must exist first). Strictly second.

## Risks specific to this aspect

- Fixtures are hand-written and can drift from what the engine emits. For the legacy case
  the fixture must be written to disk with the key **absent** — which means editing the
  JSON after `write_bundle`, since `model_dump_json` always emits the field. If that step
  is skipped the legacy tests pass vacuously.
- Text output is the product here. A correct dict rendered unreadably fails the aspect's
  actual purpose.
