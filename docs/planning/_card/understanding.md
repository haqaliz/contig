# Understanding — reproduce-case-promote (deep dig, 2026-08-15)

Source: `docs/planning/_card/issue.md` (inline brief from the contig-next recommendation),
verified against the worktree code at v0.53.0.

## What the work is really asking

The C6 eval fold-in's reproduce track shipped the guard (`contig reproduce-guard`,
13/14 baseline over 14 frozen synthetic scenarios) but **not the capture half**: the
CHANGELOG Unreleased entry says "the capture channel has NOT shipped: capture of
reproduce outcomes (pending `ReproduceCase` + promote, the capture-promote aspect)
remains the pending follow-on slice, and the corpus only becomes non-tautological as
real runs feed it through that channel." This slice ships that channel: pending
`ReproduceCase` capture from real reproduce runs + `contig reproduce-case-promote`,
mirroring the shipped verification-track machinery, without touching the signed
record and without moving the 13/14 baseline.

## What the dig found (file:line)

- **Verify-track machinery to mirror (the pattern):** `VerificationCase` model
  (`models.py:701-721`) stores **pre-band inputs** (`inputs: {family: {sample:
  {metric: value}}}`) plus `expected_verdict` assigned at promote — deliberately NOT
  the computed verdict, so the corpus is band-sensitive (a band change flips stored
  cases; the mutation-control pin `test_verify_corpus.py:66-94` proves it).
  Predicate `should_capture_verification` (`verify_corpus.py:445-462`) gates on
  green tasks + fail/warn verdict + non-empty pre-band inputs ("interesting cases
  only", always on, no flag). Builder `verification_case_from_run`
  (`verify_corpus.py:465-489`), append `append_verify_case` (`:340-345`), promote
  `promote_pending_verify_case` (`:492-531`: source `pending:`→`confirmed:`,
  dedupe by case_id, append golden + rewrite pending). Capture hook at
  `self_heal.py:1754-1765` (default `<runs_dir>/pending_verify_corpus.jsonl`).
  CLI `verify-case-promote` (`cli.py:2446-2504`): positional `case_id`,
  `--expected-verdict` (validated pass|warn|fail|unverified, exit 1 before any
  write), `--pending` (default `runs/pending_verify_corpus.jsonl`), `--golden`,
  `--history-file`; auto-snapshots the grown golden into history.
- **Reproduce track (greenfield capture):** `ReproduceRecord` (`models.py:811-830`:
  reproduce_id, repo, run_command, claims_sha256, claim_results, exit_code,
  created_at, interpreter, tool, repair_history, source_url, source_commit,
  source_tree_sha256). `run_reproduction` (`verification/reproduce.py:838-851`)
  is pure — returns the record; the ONLY persistence is the CLI bundle write
  (`cli.py:1125` `write_reproduce_bundle`), after the remote pins are patched
  (`cli.py:1112-1123`). **Zero corpus/pending hooks anywhere in the reproduce
  path** (grep-verified). `ClaimResult` (`models.py:799-808`: id, status
  `reproduced|within_tolerance|diverged|unverified`, claimed, observed, tolerance,
  delta, message) carries the per-claim observed value — the pre-classification
  input (the "pre-band" analog is (claimed, observed, tolerance) + locator family).
  `repair_history` carries the env-resurrection outcome (`installed_and_retried`
  etc.). Guard replay/scoring: `reproduce_guard.py` (`run_reproduce_scenario`
  `:91-172`, `evaluate_reproduce` `:179-273` — strict equality match per claim
  status + repair + exit code), mutation pins in `test_reproduce_guard_scorer.py:193-224`.
- **The 13/14 baseline must not move:** `reproduce-guard` defaults to the frozen
  `reproduce_scenarios.jsonl` and `reproduce-guard` docstring itself names the gap
  ("the corpus only becomes non-tautological as real runs feed it through the
  pending-capture/promote channel", `cli.py:3109-3111`). Mirror the verify-track
  rule (`verify_corpus.py:305-311`): golden corpus is deliberately never the
  guard's default.
- **ReproduceCase labeling decision (the brief's open question):** faithful mirror
  of `VerificationCase` = store **pre-classification inputs** — per-claim
  (claimed, observed, tolerance, family) — not the derived statuses; `expected`
  statuses assigned at promote; a scorer re-derives statuses under current
  classification (like the verify scorer re-derives under current packs), with a
  mutation-control pin proving a tolerance/threshold change flips a stored case.
  This keeps the corpus band-sensitive and non-tautological (the verify precedent,
  `verify_corpus.py:1-9, 66-94`).

## The design fork (for the interview)

1. **What captures:** every reproduce run, or gated on "interesting" outcomes only
   (any claim diverged/unverified, repair occurred, or non-zero exit)? Verify-track
   precedent gates (`should_capture_verification`); recommend gating.
2. **What a case stores:** (a) full pre-classification inputs per claim + repair +
   exit (band-sensitive mirror, recommended), or (b) observed statuses verbatim
   (simpler, more tautological).
3. **Capture point:** CLI after the remote pins are finalized, before/at the bundle
   write (`cli.py:1112-1125`) — the reproduce path has no `_finalize`; the record is
   the record.
4. **Promote surface:** `--expected-claims`-style labels (per-claim expected status
   + expected repair + expected exit) vs a single run-level label — verify precedent
   uses one `expected_verdict` per case; reproduce has N claims, so the label set is
   per-claim. Whether to require full labeling or allow partial.
5. **Scoring/guard:** a `evaluate_reproduce_cases` used by promote's auto-snapshot
   only (no new CI guard; the corpus starts empty), or a new guard command wired to
   CI once cases exist.

## Guardrails check

Layer 2 (eval-data capture / C6 flywheel), inside the founder's edge, no new
dependencies, test-first, no real repo/network in CI. The capture must not move the
13/14 baseline (guards default to frozen scenario corpora, never golden). Honest
scope: corpus starts empty; push, not demand-pull — record in roadmap + CHANGELOG
per house style.
