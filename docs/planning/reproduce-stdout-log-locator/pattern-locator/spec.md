# Aspect spec — `pattern-locator` (stdout/log regex locator)

Single aspect for the `reproduce-stdout-log-locator` PRD. The whole change is localized to
`src/contig/verification/reproduce.py` + `src/contig/cli.py` + tests; no `models.py`, bundle, or
signing change. Parent PRD: `../prd.md`.

## Problem slice & outcome

A `contig reproduce` claim can bind its observed value by regex capture over the run's captured
combined stdout+stderr (`pattern`, no `from`) or over a repo-relative text/log file (`from` +
`pattern`). Every unresolved / ambiguous / non-participating / oversized / unparseable address →
UNVERIFIED, never a false reproduce, never DIVERGED.

## In scope

- `PatternLocator(source: str | None, pattern: str)` dataclass; widen `Claim.locator` to
  `Locator | TableLocator | PatternLocator | None`.
- `load_claims` pattern validation: three-way mutual exclusion with `path` and `column`/`row`;
  non-empty string; **compiles** (`re.error` → `ClaimsError`); the orphan guard relaxed for
  `pattern` **only**.
- A pure, never-raising `resolve_match(text, pattern) -> tuple[str | None, str]`: strict 0-or-many
  → `(None, reason)` with the count; group 1 else whole match; non-participating group →
  `(None, reason)`.
- Nested `_observe_pattern_located`: stdout mode (closes over `run_output`) and file mode
  (containment guard + `stat()` size check + `_text_cache`), then strip → `float()` → finite guard.
- Explicit isinstance dispatch at the per-claim branch (replacing the unguarded `else`).
- CLI containment loop skips a `source is None` locator; CLI docstring note.
- `_MAX_MATCH_BYTES = 8 MiB` bound.

## Out of scope

Everything in the PRD's "Out of Scope": `occurrence`/`group`/`flags` keys, notebooks, prose,
figures, scraping a failed run, persisting output on the record, new deps, model/bundle changes,
other slices.

## Acceptance criteria (testable — PRD G1–G7, R5, R6 + critique gap #1)

- stdout-mode claim (no `from`) → REPRODUCED / WITHIN-TOLERANCE / DIVERGED, with **no** results
  file present.
- file-mode claim (`from` + `pattern`) → resolves from an on-disk fixture log.
- 0 matches → UNVERIFIED, message names "0"; N>1 matches → UNVERIFIED, message names N.
- Pattern with no groups → whole match is the value; with groups → group 1.
- **Non-participating capture group → UNVERIFIED, never `TypeError`.**
- Uncompilable pattern → `ClaimsError` at load; CLI exits non-zero and writes **no** record.
- `pattern` + `path`, or `pattern` + `column`/`row` → `ClaimsError`. `pattern` alone (no `from`) is
  **legal**; `path`/`column`/`row` alone (no `from`) stays an error.
- Escaping/absolute `from` on a pattern claim → CLI exit non-zero, no record; engine defensive
  UNVERIFIED with the file never read. A `from`-less claim never touches the filesystem.
- Under `--allow-install`, a stdout claim binds from the **retried** run's output.
- Non-zero exit → all unverified (unchanged short-circuit).
- Oversized text (> 8 MiB) → UNVERIFIED naming the size; an oversized file is never read.
- Same file, two pattern claims → read once (`_text_cache`).
- A `PatternLocator` never reaches `_observe_located` (the JSON reader).
- JSON-locator + table-locator + flat claims and all existing suites unchanged and green
  (baseline **1829 passed, 1 skipped**).
- No dependency added; `models.py` untouched.

## Sequencing

Phases are sequential (all touch `reproduce.py`): Schema → Pure resolver → Engine branch →
CLI + e2e → Polish/docs. One agent per phase, strict TDD, commit per phase.

## Aspect risks

- `source: str | None` meeting three unconditional `repo_path / loc.source` joins is the likeliest
  crash/containment hole (PRD R5).
- The unguarded dispatch `else` would misroute the new type into the JSON reader (PRD R6).
- A non-participating capture group is the likeliest `TypeError` in the resolver.
- Parallel edits to `reproduce.py` would conflict → phases run sequentially, not fanned out.
