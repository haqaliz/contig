# Task 5 report — Phase 5: docs, CHANGELOG, roadmap (C8 slice 3)

Date: 2026-07-21 · Feature: `reproduce-tsv-csv-locator` (C8 slice 3) · Phase: 5 of 5
(docs only — no `src/`/`tests/` change).

## Scope

Phase 5 is documentation-only, per the plan. No behavior change. Confirmed via `git status`
before and after: only `CHANGELOG.md` and `docs/technical/CAPABILITY_ROADMAP.md` were edited
by this task (plus pre-existing, unrelated dirty files `docs/planning/_card/issue.md`,
`docs/planning/_card/understanding.md`, `uv.lock`, which predate this task and were left
untouched).

## Files edited

- `/Users/aliz/dev/at/contig/.claude/worktrees/feat-reproduce-tsv-csv-locator/CHANGELOG.md`
  — added an `### Added` entry under `## [Unreleased]` describing the TSV/CSV table-cell
  locator: the claim shape (`{"from", "column", "row", "header"?, "delimiter"?}`), the two
  addressing modes, the new pure stdlib reader (`_read_table` + `resolve_cell` +
  `_resolve_delimiter`), `load_claims`'s structural pre-run validation, the engine dispatch
  (`_observe_table_located` + `_table_cache`), the deliberate numeric-string divergence from
  the JSON locator rule, the honesty contract (every unresolved/ambiguous address →
  UNVERIFIED, never DIVERGED), what's reused unchanged (`classify`, models, bundle, signing,
  `--fail-on-diverged`, no `models.py` change), stdlib-only (no new dep), and the deferred
  items (multi-key/predicate rows, stdout/notebook scraping, figure/table-image claims —
  still hard-blocked on no plot-hash — paper-parsing, remote `<doi|url>`, dashboard card, C6
  fold-in), plus the "no real repo/network in CI, fixture tables only" honesty note.
- `/Users/aliz/dev/at/contig/.claude/worktrees/feat-reproduce-tsv-csv-locator/docs/technical/CAPABILITY_ROADMAP.md`
  — in the C8 section:
  - Updated the C8 header line to add `+ TSV/CSV table-locator slice 3 SHIPPED (Unreleased)`.
  - Added a new `**Shipped (TSV/CSV output-locator — slice 3, Unreleased).**` paragraph
    (mirroring the slice-1.5 paragraph's structure and tone) after the environment-resurrection
    (slice 2) paragraph and before the "Correction to the build surface below" note.
  - Removed `TSV/CSV locator (the named next step)` from the three deferred-lists it appeared
    in: the slice-1.5 paragraph's `**Deferred:**` sentence, the slice-2 paragraph's
    `**Deferred:**` sentence, and the C8 row of the sequencing-summary table. Every other
    deferred item in those lists (import→package alias map, iterative multi-module resolution,
    version pinning, venv isolation, paper-parsing, figure/plot claims, remote fetch, dashboard
    card, C6 fold-in, etc.) was left unchanged.
  - Updated the C8 sequencing-summary table row (`| C8 | ... |`): added
    `+ TSV/CSV table-locator slice 3 SHIPPED (Unreleased)` to the Window column, and added a
    `**+ TSV/CSV table locator (slice 3):**` sentence to the Leverage column summarizing the
    shipped slice, before the (now TSV/CSV-locator-free) `**Deferred:**` list.

## Verify

- `git grep -n "TSV/CSV locator (the named next step)"` — **no matches** (exit code 1),
  confirming the deferral text is fully removed now that the slice has shipped.
- `uv run pytest --tb=short -rN` (full suite, after the docs edits, no code touched):
  ```
  1826 passed, 1 skipped in 13.02s
  ```
  Matches the pre-Phase-5 baseline exactly (0 regressions, 0 new tests — expected, since this
  phase adds no tests and no behavior).
- No `src/` or `tests/` file was modified; `pyproject.toml` and the package version were not
  touched (release is a separate step per `RELEASING.md`).

## Concerns

None blocking. This phase was purely additive prose in two Markdown files; no code, schema,
or test changed.
