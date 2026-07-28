# Aspect spec — `locator` (TSV/CSV cell locator)

Single aspect for the `reproduce-tsv-csv-locator` PRD. The whole change is localized to
`src/contig/verification/reproduce.py` + `src/contig/cli.py` + tests; no `models.py`,
bundle, or signing change. Parent PRD: `../prd.md`.

## Problem slice & outcome

A `contig reproduce` claim can bind its observed value from a cell in a repo's own
`.tsv`/`.csv`(+`.gz`) output, addressed by (named) header-column + row-key-match or
(positional) integer column + integer row. Every unresolved/ambiguous/unparseable address
→ UNVERIFIED, never a false reproduce.

## In scope

- `TableLocator` dataclass; widen `Claim.locator` to `Locator | TableLocator | None`.
- `load_claims` table-locator validation (structural, repo-agnostic) incl. delimiter
  resolution (extension or explicit; unknown extension + no delimiter → `ClaimsError`).
- A pure cell resolver over parsed rows + a gzip-transparent stdlib file reader.
- `run_reproduction` isinstance dispatch to a table reader sibling of `_observe_located`,
  with a per-file table cache.
- CLI containment loop learns table locators (reuse `.source`); help/docs note.

## Out of scope

Everything in the PRD's "Out of Scope": multi-key/predicate rows, prose/plot/notebook,
new deps, model/bundle changes, other slices.

## Acceptance criteria (testable — all in the PRD's G1–G6 + R1/R6/R7)

- Named table claim → REPRODUCED / WITHIN-TOLERANCE / DIVERGED (fixture repo, engine+CLI).
- Positional + `header:false` claim → resolves a cell by integer indices.
- gzip (`.tsv.gz`/`.csv.gz`) read transparently.
- Row-key 0-match and >1-match → UNVERIFIED with the count in the message.
- Column-name-absent / duplicate-header / index-out-of-range / ragged-row / empty-file /
  header-only / directory-`from` / non-utf8 / unparseable-cell / non-finite → UNVERIFIED,
  never raises, never DIVERGED.
- `path` + table fields mixed → `ClaimsError`; `row`-object + `header:false` → `ClaimsError`;
  unknown extension + no `delimiter` → `ClaimsError`. All pre-run, no record.
- Escaping/absolute table `from` → CLI exit non-zero, no record; engine defensive UNVERIFIED.
- JSON-locator + flat-`results.json` + all existing suites unchanged and green.
- No dependency added; `pyproject.toml` runtime deps unchanged.

## Sequencing

Phases are sequential (all touch `reproduce.py`): Schema → Pure reader → Engine branch →
CLI + e2e → Polish/docs. One agent per phase, strict TDD, commit per phase.

## Aspect risks

- Ragged-row `IndexError` is the likeliest crash — the pure reader must be index-safe.
- Parallel edits to `reproduce.py` would conflict → phases run sequentially, not fanned out.
