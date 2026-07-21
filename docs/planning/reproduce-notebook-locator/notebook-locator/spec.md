# Aspect spec — notebook-locator

The sole aspect of `reproduce-notebook-locator`. The PRD
(`docs/planning/reproduce-notebook-locator/prd.md`) is the requirements source; this spec
scopes the one buildable unit.

## Problem slice & user outcome

`contig reproduce` cannot read a Jupyter `.ipynb`, so every claim against a published
notebook degrades to `UNVERIFIED`. Outcome: a claim carrying
`{"from": "<x.ipynb>", "cell": …, "pattern": …}` binds its observed value out of the
addressed cell's output and classifies through the unchanged `classify` — with a freshness
guard that refuses a notebook the run did not rewrite.

## In scope

- `NotebookLocator(source, cell, pattern)` dataclass (PRD M1).
- `cell: int | {"contains": str}` addressing over the full `cells` array (M2).
- Output-text extraction: stdout streams + `text/plain`, in order (M3).
- `pattern` required, capture via shipped `resolve_match` (M4), slice-3/4 numeric rule (M5).
- mtime freshness guard, non-bypassable, run-start injected (M6, M6a).
- Four-way `load_claims` exclusion, pre-run (M7).
- Never-raise pure resolver, containment + size bound + per-run cache (M8, M9).

## Out of scope

Everything in the PRD's Out of Scope: notebook execution, committed-output evidence,
non-text outputs, structure verification, paper-parsing, remote fetch, dashboard, C6 fold-in.

## Acceptance criteria (testable)

1. Pure extractor returns `(text, "")` for a resolvable cell/output and `(None, reason)` for
   every unresolved shape, never raising.
2. A notebook claim classifies at all four verdicts through `classify`.
3. **A stale notebook (mtime < run-start) is `UNVERIFIED` even when its stored output matches
   the claim exactly** — the load-bearing test.
4. `load_claims` rejects every malformed notebook claim as a `ClaimsError` (exit 1, nothing
   written); a `pattern`+`from` claim without `cell` stays a slice-4 `PatternLocator`
   (byte-identical back-compat).
5. Full suite green, no new dependency, no `models.py` change.

## Dependencies & sequencing

Pure resolver → schema validation → engine dispatch + guard → CLI wiring/docs. Each phase
is RED→GREEN before the next.

## Open questions

- Message wording for a markdown cell (no `outputs` key) vs an empty `outputs` list — cosmetic
  (PRD R6); pick one message and note it.
