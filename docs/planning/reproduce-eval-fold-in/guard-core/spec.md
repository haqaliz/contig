# Aspect spec: guard-core

Aspect of `reproduce-eval-fold-in` (PRD: `docs/planning/reproduce-eval-fold-in/prd.md`).

## Problem slice

The `contig reproduce-guard` regression guard: frozen reproduction scenarios
replayed through the **real** `run_reproduction` loop, guarding a per-scenario
outcome-match rate against a committed baseline, wired into CI — the fourth
guard sibling of `eval-guard` / `heal-guard` / `verify-guard`.

## In-scope

- `ReproduceScenario` + `ExecStep` + `ReproduceSnapshot` models (additive,
  back-compat) in `models.py`.
- `src/contig/reproduce_guard.py`: scenario driver (scripted executor/installer
  built from the scenario, claims validated through the **real** `load_claims`,
  replay through the **real** `run_reproduction` with only the
  executor/installer seams injected), scorer (`evaluate_reproduce` — exact
  per-claim status equality + repair + exit code, per-family informational
  rates), baseline/history I/O, comparator.
- Frozen corpus `src/contig/data/reproduce_scenarios.jsonl` (~14 scenarios
  covering flat results, JSON/table/pattern(file+stdout)/notebook locators,
  stale-artifact UNVERIFIED, env-resurrection heal + install-fail give-up,
  non-zero exit, one `known_miss` keeping the baseline < 1.0).
- Committed baseline `src/contig/data/reproduce_baseline.json` (refrozen
  deliberately via `--update-baseline`, never hand-edited) and append-only
  history `src/contig/data/reproduce_history.jsonl`.
- `contig reproduce-guard` CLI command mirroring `verify-guard`
  (`cli.py:2920-3068`): `--scenarios` / `--baseline` / `--tolerance` /
  `--update-baseline` / `--json` / `--snapshot` / `--history` / `--history-file`;
  exit 1 on regression.
- CI step in `.github/workflows/ci.yml` beside the three existing guard steps.
- Honest-scope records: CAPABILITY_ROADMAP.md (C6/C8 rows) + CHANGELOG
  Unreleased.

## Out-of-scope boundaries

- No capture/promote channel (aspect `capture-promote`).
- No fetcher/network/git; scenarios are local temp-dir replays only.
- No CLI-layer coverage (refusals, containment — already unit-tested).
- No changes to `classify`, `run_reproduction`, `load_claims`, the locators, or
  the freshness guard. The guard reuses them verbatim.
- No signature changes, no new dependencies (stdlib-only).

## Acceptance criteria (testable)

1. `uv run contig reproduce-guard` exits 0 at the committed baseline; a
   deliberately broken scenario (or a mutated expected status) exits 1.
2. The guarded rate counts a scenario as matching only when **every** expected
   per-claim status, the expected repair, and the expected exit code match —
   `UNVERIFIED` never counts as reproduced.
3. Anti-tautology mutation control: editing one expected status in a frozen
   scenario flips that scenario's match (pinned test, the
   `tests/test_verify_corpus.py:66-94` precedent).
4. A stale-artifact scenario yields UNVERIFIED (freshness guard exercised); a
   fresh-artifact scenario yields its declared statuses.
5. Every locator family (`flat`, `json`, `table`, `pattern`, `notebook`) has ≥ 1
   scenario; per-family rates appear in the snapshot.
6. `--update-baseline` refreezes and appends history; `--snapshot` appends
   only; `--history` renders; `sha_mismatch` is a non-failing warning;
   history is append-only and never rewritten.
7. No real repo, git, network, or pip anywhere in CI for this aspect; suite
   stays green (full `uv run pytest`).

## Dependencies & sequencing

- First aspect of the feature. `capture-promote` depends on this aspect's
  `evaluate_reproduce` + snapshot machinery for its promote auto-snapshot.
- Reference modules to mirror: `src/contig/verify_corpus.py` (scorer + I/O +
  comparator), `src/contig/heal.py` (scenario driver), `src/contig/snapshot_history.py`.
- Replay fixture shape: `tests/test_reproduce_env_resurrection.py:80-126`
  (`_ScriptedExecutor` / `_ScriptedInstaller`, `_RUN_START = 1_000_000.0`).

## Open questions / risks

- **Freshness interplay (the known risk):** artifacts must be written *during*
  the scripted executor call with `os.utime` mtime **exactly equal to** the
  injected `run_started_at` (the shipped `>=` boundary pin, test_reproduce.py
  freshness tests) — a stale artifact silently yields 100% UNVERIFIED.
- Exact `RepairStep.outcome` literal names for the repair mapping must be
  verified against the code at implementation time (env-resurrection slice:
  `installed_and_retried` / `install_failed` / `retry_failed`).
- Baseline numbers must be read from the frozen run's own output, never
  hand-written (heal-guard precedent).
