# Understanding — match-and-propose (C8 locator-inference aspect 2 of 3)

Unit: `feat/reproduce-locator-matcher/aliz`. Source: handoff brief (contig-next
pick), PRD `docs/planning/reproduce-locator-inference/prd.md`. Phase-2 dig by an
explore agent, verified against the worktree code (all PRD file:line citations
checked accurate).

## What the work is really asking

Close the last manual link in the paper → verdict chain: a human currently
hand-writes a locator per extracted claim before `contig reproduce` can bind
anything. Aspect 2 is the **pure matcher**: consume the shipped `sweep_repo`
candidate enumeration (`src/contig/verification/locator_inference.py`, shipped
Unreleased) plus an `extract-claims` draft, and propose a binding site **only on
unambiguous evidence** — strict exactly-one, dual-scale `v`/`v÷100` disclosed,
complete-or-nothing locators, M9 low-information-value refusal, G1 (0 wrong
locators on the fixture corpus) as the hard gate. Evidence-gated search, never
inference from the paper (the PRD's "inventing a locator would be dishonest"
objection is sidestepped, not overturned — `prd.md:29-39`).

## Scope boundary (from the PRD decomposition)

- **In:** aspect 2 = pure matcher module, no I/O, fully CI-testable. It feeds the
  **evidence gate** (one real published repo, count binds/ambiguities/refusals,
  report any R6 fresh-path mismatch) which must run and be recorded before aspect
  3 (the CLI) starts.
- **Out:** the CLI (`contig infer-locators`, aspect 3, gated); `pattern`/notebook
  inference (blocked: synthesized regex vs `resolve_match`'s exactly-one rule,
  `prd.md:173-179`); figure/plot claims (hard-blocked, no plot-hash); any
  `models.py` / verdict / bundle / signature change; any modification to
  `extract-claims` or its `{"id","value","tolerance"}` draft contract (pinned by
  `tests/test_cli_extract_claims.py:104`).

## Affected areas (verified against current code)

- `src/contig/verification/locator_inference.py` (938 lines, aspect-1 shipped) —
  the consumed surface: `Candidate(source, kind, value, path|column|row|header)`
  frozen dataclass (L83-91; JSON int leaves stored as `int`, table values always
  `float`), `SweepSkip(source, reason)`, `sweep_repo(repo) -> (candidates, skips)`
  (L837-938), `iter_artifacts` (L100-230). Candidates are sorted by POSIX
  `source`; `source` is verbatim the locator `from`; JSON paths are dotted+`[n]`
  strings already round-trip-pinned through the shipped `_parse_path`.
- `src/contig/verification/reproduce.py` — the round-trip targets (unchanged):
  `Locator`/`TableLocator`/`PatternLocator`/`NotebookLocator`/`Claim` frozen
  dataclasses (L156-219, L518-535), `load_claims` xor traps (L538-801; table
  locators must be complete: `from`+`column`+`row`, bool `header`, str column ⇒
  header=True; JSON = `from`+`path`), `classify` (L804-842), `_require_fresh`
  nested inside `run_reproduction` (L890, not importable — inference structurally
  cannot weaken it; a stale artifact still yields UNVERIFIED at reproduce time).
  Emitted locators must also classify under `reproduce_guard.py:81-95`
  (`claim_family` dispatch).
- `src/contig/verification/claim_extraction.py` — draft claims carry
  `value: float`, `tolerance: float` (default 0.1); percentages are the raw
  number, never ÷100 (so the matcher's ÷100 attempt is against the *repo*
  artifact scale, not the draft's).
- Tests: `tests/verification/test_locator_sweep.py` (fixture style = inline
  `tmp_path` repos; universal round-trip pins) is the precedent for the matcher's
  suite. No `tests/fixtures/` repo exists for this feature (PRD open question).

## Ambiguities / open questions for the interview

1. **R3 — float-precision recovery**: "rounded to the claim's printed precision"
   from a parsed float has repr edge cases; may need the draft's raw token rather
   than the float. The draft JSON stores `value` as a number — the raw token is
   available in the claims *file* text, not in the parsed `Claim`. Decide: parse
   the raw token from the file, or derive precision from the float's repr
   (recommended: float-repr with a floor/ceil guard, pinned by tests).
2. **Fixture style**: inline `tmp_path` repos (sweep precedent) vs a committed
   fixture repo at `tests/fixtures/` (`prd.md:256`). Recommend inline — the sweep
   precedent, zero cross-test coupling.
3. **Sidecar wording + scope**: aspect 2 is module-only (no CLI) — does the
   per-claim sidecar/provenance text (S2) ship here as a pure rendered string the
   CLI consumes later, or is it deferred to aspect 3? Recommend: a pure
   `sidecar_text` builder here (testable now, CLI renders it later).
4. **`--dry-run` (S4)**: PRD leaves it open; it is CLI surface — defer to aspect 3.
5. **Module placement**: new `verification/locator_match.py` (sibling of
   `locator_inference.py`), reusing the import-only discipline (never edit
   `reproduce.py`).

## Contradictions surfaced (not papered over)

- The PRD's "Proposed aspect decomposition" (L274-293) reads as forward-looking;
  aspect 1 is now **shipped** (module + `tests/verification/test_locator_sweep.py`).
  The actionable remainder is exactly aspect 2 + the evidence gate before aspect 3.
- PRD R2 (recall may be low) is mitigated by the evidence gate sequencing: a dead
  end costs two pure modules, not the slice. R6 (stale-coordinate/fresh-path
  mismatch) is accepted-and-disclosed, **not** solvable in this aspect; the
  sidecar must state per claim the exact path whose rewriting the locator depends
  on, and the evidence-gate record must report it.

## Guardrails check (CLAUDE.md)

Layer 2 (verify/reproduce machinery) ✓. Never Layer 1 — this proposes binding
sites for existing resolvers; it authors nothing ✓. Founder's edge — no
wet-lab/clinical credentials, no proprietary data, no regulatory ✓. Test-first,
synthetic fixtures, deterministic, no network in CI ✓. Not blocker-deferred work
(the blocked halves — pattern/notebook, figures — are explicitly excluded, and
the exactly-one rule collision is named, not hidden) ✓.