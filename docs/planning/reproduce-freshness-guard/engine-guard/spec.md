# Aspect spec — `engine-guard`

Sole aspect of `reproduce-freshness-guard`. The PRD change is one indivisible edit to
`src/contig/verification/reproduce.py` plus its test suite; splitting it into further aspects
would produce a half-guarded engine at every intermediate commit, which is exactly the
inconsistent state R2 filed against.

## Problem slice and user outcome

Four of `contig reproduce`'s five disk-reading binding paths bind a claim's value without
checking the run wrote the file, so a committed artifact reports `REPRODUCED`. After this
aspect, every disk-reading path requires the artifact's mtime to be `>= run_started_at`, and
a stale artifact is `UNVERIFIED` naming the reason.

## In scope

- A shared freshness helper inside `run_reproduction`.
- Guard wired into `_observe_located` (JSON), `_observe_table_located` (TSV/CSV),
  `_observe_pattern_located` **file mode only**, and the flat `--results` read.
- A distinct stale message for the flat results path (never "missing or unparseable").
- `ValueError` on a guarded branch when `run_started_at is None`.
- Test-suite migration + one headline stale test per newly guarded surface.
- CLI docstring, CHANGELOG, `CAPABILITY_ROADMAP.md` C8 entry.

## Out of scope

Everything in the PRD's Out of Scope, plus: no change to the notebook branch's behavior
(only a refactor to share the helper), and no `models.py` change.

## Acceptance criteria

The PRD's 8 acceptance criteria, unchanged, all `uv run pytest`-verifiable.

## Dependencies and sequencing

No external dependency. Internal sequencing is strict and stated in the plan: the test-helper
stamp migration (Phase 0) **must** land before the first guard, or the suite goes red for
reasons unrelated to the change under test.

## Aspect-specific risks

- **R4 (symlinks)** and **R5 (clock skew)** from the PRD are decided in the plan, not left open.
- The Phase 0 ordering constraint is the main way this aspect can go wrong in execution.
