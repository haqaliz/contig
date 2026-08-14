# PRD: reproduce-eval-fold-in

Status: draft for review (Phase 3 of `cbf feat reproduce-eval-fold-in`).
Owner: aliz. Slug dir: `docs/planning/reproduce-eval-fold-in/`.

## Problem Statement

The reproduce track (C8) is the only shipped Layer-2 surface with **no
regression guard of its own**. `eval-guard`, `heal-guard`, and `verify-guard`
each freeze a corpus and fail CI when the engine's behavior on it degrades
(`docs/technical/CAPABILITY_ROADMAP.md` C6 slices 1–2, v0.51.0 fold-in);
reproduce has none — a regression in `classify`, a locator, or the
env-resurrection seam would ship unnoticed. Meanwhile C8's own roadmap promise
is unmet: "every reproduction attempt (the environment-repair chain, the
per-claim diff outcome) is a labeled corpus case — a whole new, publicly-sourced
stream of failure-and-fix data feeding C6" (CAPABILITY_ROADMAP.md C8), and the
"C6 eval fold-in" sits in the deferred list of nearly every C8 slice (1, 1.5, 3,
4, 5, 6, 8, extract-claims).

This card builds both halves: a `contig reproduce-guard` that replays frozen
reproduction scenarios through the **real** reproduce machinery and guards a
per-claim verdict-match rate against a committed baseline (wired into CI), and a
capture channel that turns every `contig reproduce` run into a pending corpus
case promoted by a human into a golden corpus.

## Goals & Success Metrics

| Goal | Metric | Target |
|---|---|---|
| Reproduce regressions fail CI | `reproduce-guard` exit code + committed baseline | Guard wired into `.github/workflows/ci.yml`; regression (below baseline − tolerance) exits 1 |
| Guard is live, not tautological | Anti-tautology mutation control test | A deliberate expected-status edit flips a scenario's match (pinned test) |
| Corpus captures every run | Capture appends per reproduce run | `pending_reproduce_corpus.jsonl` grows one line per `contig reproduce`; promoted via CLI |
| Honest, never a false pass | Guarded number's semantics | Exact per-claim status equality; UNVERIFIED never counts as reproduced; baseline starts < 1.0 via one deliberate known-miss scenario |
| Deterministic, offline CI | No real repo/network/pip in CI | All scenarios replay through scripted executors/installers with injected clocks |

## User Personas & Scenarios

Internal feature. The "user" is the Contig engine and the founder's CI.

- **Engine**: `contig reproduce-guard` is a build step; a red run means a
  reproduce behavior regression shipped.
- **Founder / maintainer**: `--update-baseline` refreezes deliberately;
  `--history` shows the trend; the capture+promote channel grows the
  publicly-sourced reproduce corpus (moat #2) with real runs.

## Requirements

### Must-have

1. **`contig reproduce-guard` command** (sibling of `eval-guard`/`heal-guard`/
   `verify-guard`): replays a frozen `reproduce_scenarios.jsonl` through the
   **real** `run_reproduction` loop — real `load_claims`, real `classify`, real
   locators, real `_require_fresh` freshness guard, real env-resurrection logic —
   with only the `executor`/`installer` seams injected as scripted fakes (the
   established seam contract, `reproduce.py:838-851`).
2. **`ReproduceScenario` model** and frozen corpus
   (`src/contig/data/reproduce_scenarios.jsonl`), one scenario per locator
   family + the repair/give-up paths:
   - flat `--results` exact match → REPRODUCED; within-tolerance → WITHIN-TOLERANCE;
     diverged → DIVERGED
   - JSON locator, table locator, pattern locator (file + stdout), notebook locator
   - freshness-stale artifact → UNVERIFIED (never a false pass)
   - env-resurrection heal (`installed_and_retried`) and install-fail give-up
   - non-zero exit → all claims UNVERIFIED
   - one deliberate **known-miss** scenario keeping the committed baseline < 1.0
3. **Match semantics (confirmed): exact per-claim status equality.** A scenario
   matches iff every expected per-claim status (REPRODUCED / WITHIN-TOLERANCE /
   DIVERGED / UNVERIFIED), the expected repair outcome, and the expected exit
   code match. Guarded number = `outcome_match_rate` (matched scenarios /
   total), computed over the **re-derived** statuses — never stored ones.
   Per-claim rates and per-locator-family rates are informational.
4. **`ReproduceSnapshot` baseline + history**, matching sibling invariants:
   single pretty-printed baseline JSON (`reproduce_baseline.json`), JSONL
   history (`reproduce_history.jsonl`), `corpus_sha` pinning, `--update-baseline`
   / `--snapshot` / `--history` / `--history-file` / `--tolerance` flags, exit 1
   on regression, informational `sha_mismatch` warnings.
5. **CI wiring**: `- run: uv run contig reproduce-guard` in
   `.github/workflows/ci.yml` beside the three existing guard steps.
6. **Capture channel (confirmed: every run)**: the `contig reproduce` command
   appends one `ReproduceCase` (per-claim statuses, observed/claimed values,
   deltas, locator family, repair chain summary from
   `ReproduceRecord.repair_history`, exit code, `claims_sha256`) to
   `<runs_dir>/pending_reproduce_corpus.jsonl` at bundle-write time — a sidecar
   append that **never touches the signed `ReproduceRecord` or
   `signature.json`**.
7. **`contig reproduce-case-promote` CLI** (mirror of `verify-case-promote`,
   `cli.py:2434-2492`): load pending, dedupe against golden
   (`src/contig/data/reproduce_corpus.jsonl`), set `--expected-verdicts
   <claim_id:status,...>` (omitting = confirm unlabeled) and `--expected-repair`,
   flip `pending:` → `confirmed:`, rewrite pending, append to golden, auto-snapshot
   the grown golden into `reproduce_history.jsonl`.
   **Ground-truth contract, stated honestly:** a promoted label means "a human
   reviewed this run's per-claim verdicts and they stand" — an audit trail, not
   new ground truth. Corrections happen where a locator bound the wrong value
   (the human sees the observed value and can correct the expected status); the
   engine's own classification is deterministic and usually right. A
   `--confirm-all` flag (promote every pending case with its engine-derived
   expected statuses) covers the common batch case; per-claim `--expected-verdicts`
   remains for the locator-correction case.
8. **Honest-scope records**: CAPABILITY_ROADMAP.md C8/C6 and CHANGELOG updated
   with the fold-in shipped + the self-graded/synthetic caveat, per house style.

### Should-have

9. Per-family (`flat`, `json`, `table`, `pattern`, `notebook`) informational
   rates in the snapshot, so a locator-family regression is diagnosable from one
   guard run.
10. Anti-tautology mutation control test in the suite: an edit to an expected
    status (or to `classify`'s tolerance path) flips the predicted match — the
    verify-guard precedent (`tests/test_verify_corpus.py:66-94`).

### Nice-to-have

11. `--detector`-style family filter to run one family's scenarios locally.
12. Dashboard trend card for reproduce (explicitly deferred to a later card).

## Technical Considerations

- **New module** `src/contig/reproduce_guard.py` following `verify_corpus.py`:
  scenario driver (`run_reproduce_scenario`), scorer (`evaluate_reproduce`),
  baseline/history I/O, comparator (`compare_reproduce_to_baseline`).
- **Models** (all additive, back-compat): `ReproduceScenario`,
  `ReproduceSnapshot`, `ReproduceCase` in `models.py`; `FailureClass` untouched.
- **Determinism and the freshness guard (the nearest feasibility risk).**
  `run_reproduction` raises on `run_started_at=None` and marks any artifact with
  `mtime < run_started_at` UNVERIFIED (`reproduce.py:880-919`). The scenario
  driver must therefore stamp `run_started_at` (injected clock, the
  `1_000_000.0` convention used repo-wide) and the scripted executor must write
  its artifacts **during** the executor call with `os.utime`-set mtimes ≥ the
  stamp — the exact shape `_ScriptedExecutor` in
  `tests/test_reproduce_env_resurrection.py:80-126` already implements. Stdout
  mode (`PatternLocator(source=None)`) is exempt by construction and is a cheap
  source of fresh scenarios.
- **No fetcher, no network, no CLI layer.** Scenarios are local-path-only and
  drive `run_reproduction` directly (the CLI's refusal/containment logic is
  already unit-tested and does not affect verdicts; `fetch_repo` runs at the CLI
  level and is out of scope).
- **Anti-tautology contract (the fold-in's load-bearing rule).** The scorer
  re-derives every status through the **real `classify`** from stored per-claim
  *inputs* — `(claimed, observed, tolerance, family)` — never from a stored
  status (CHANGELOG v0.51.0; the verify mutation control precedent,
  `tests/test_verify_corpus.py:66-94`). `ReproduceCase` therefore stores inputs,
  not statuses; `expected_claim_statuses` is the only stored status, and it is
  the human's label, never the engine's output.
- **No signature break.** Capture writes a new sidecar file only; the signed
  canonical payload of `ReproduceRecord` is byte-identical
  (`signing.py:55-64`).
- **Stdlib-only holds** (no new dependencies; `cryptography` already present).
- **Reuse**: `benchmark._relative_delta`, `load_claims`, `classify`,
  `reduce_reproduction`, `_ScriptedExecutor` shape, `snapshot_history`
  primitives, `verify-case-promote` flow.

## Risks & Open Questions

- **Doc drift trap** (known from heal-guard: docstring says 21 scenarios/15
  classes while the baseline carries 22/16). The PRD/plan must pin scenario
  counts to the baseline JSON, and the new guard's docstring must be written
  from the shipped files, not prose.
- **Freshness-guard interplay** (above) is the one design point where a naive
  fixture (pre-written artifacts) silently produces 100% UNVERIFIED. The plan
  must include a scenario proving a *fresh* artifact classifies REPRODUCED and a
  *stale* one UNVERIFIED.
- **Baseline starts self-graded**: the frozen scenarios are authored fixtures,
  the exact honest scope v0.51.0 recorded for verify-guard; the number only
  becomes non-tautological as real runs are promoted through the capture
  channel. Recorded, not softened.
- **History trend semantics.** `reproduce_history.jsonl` receives both
  `reproduce-guard --snapshot` lines (holdout corpus) and promote auto-snapshots
  (golden corpus) — the pre-existing `verify_history.jsonl` design, inherited
  deliberately. The trend line mixes two populations; the snapshot's
  `corpus_sha` distinguishes them. Stated, not papered over; a split is a
  later-card change to all four guards together.
- **Push, not demand-pull**: no design partner asked; organic reproduce-run
  volume is unmeasured. A committed revisit trigger (e.g. guard fires on zero
  non-authored runs within N real runs) should be recorded like the siblings'.
- **Known-miss selection**: the deliberate mismatch must fail *for a reason*
  (e.g. expected WITHIN-TOLERANCE on a value that classifies DIVERGED) so the
  known-miss itself is pinned by a test, not silent.

## Out of Scope

- Reproduce **dashboard card** and C6 trend card for reproduce (deferred).
- PDF / DOI / paper-fetching and figure/plot claims (hard-blocked on the
  stdlib-only dependency decision, CAPABILITY_ROADMAP.md C8 correction).
- `reproduce-local-tree-hash` (in-flight worktree
  `feat/reproduce-local-tree-hash`, orthogonal).
- Verify-time concordance capture (`concordance_genotype` /
  `concordance_spearman`, CHANGELOG v0.53.0 deferral).
- CLI refusal/containment coverage, `fetch_repo`/`--rev`/`--allow-fetch`
  paths, signing changes, new assay work, Layer-1 anything.
- C2-style repair catalog breadth.

## Data Model (summary)

- `ReproduceScenario` (frozen, JSONL): `scenario_id`, `description`, `source`
  (`"holdout:synthetic"`), `run_command`, `claims: list[dict]` (validated
  through the real `load_claims`), `results_path`, `executor_steps:
  list[ExecStep]` (`{exit_code, output, write_results: dict | None,
  write_artifacts: {path: content} | None, artifact_mtimes: {path: float} |
  None}`), `installer_steps: list[int] | None`, `allow_install: bool`,
  `expected_claim_statuses: dict[claim_id, status]`, `expected_repair:
  "none" | "installed_and_retried" | "install_failed" | "retry_failed"`,
  `expected_exit_code: int`, `known_miss: bool = False`.
- `ReproduceSnapshot`: `timestamp`, `scenario_count`, `corpus_sha`,
  `outcome_match_rate`, `recovery_rate`, `per_family:
  dict[family, {matched, total, rate}]`, `covered_families: list[str]`,
  `contig_version`.
- `ReproduceCase` (pending/golden): `case_id`, `source`
  (`"pending:<id>" | "confirmed:<id>"`), `reproduce_id`, `repo`, `run_command`,
  `claims_sha256`, `claim_inputs: list[{claim_id, claimed, observed, tolerance,
  family}]` (inputs only — the scorer re-derives statuses through the real
  `classify`, never from stored statuses), `repair: {class, operation, outcome}
  | None`, `exit_code`, `created_at`, `expected_claim_statuses: dict | None`,
  `expected_repair: str | None` (both None until promoted).

## Non-Functional Requirements

- Deterministic: injected clock + scripted seams + `os.utime` artifact mtimes;
  no wall-clock dependence in the guard.
- Offline CI: no real repo, git, network, or pip.
- Test-first throughout; suite stays green per task.
- Back-compat: all new fields default to `None`/`False`; existing signed
  bundles load unchanged and still verify.

## Sequencing / Aspects (for tech-plan)

Rough effort: ~1.5–2 workdays across two aspects, one agent each, built
sequentially (aspect 2 depends on aspect 1's models but not its CLI).

1. **`guard-core`** (M): `ReproduceScenario`/`ReproduceSnapshot` models,
   `src/contig/reproduce_guard.py` (scenario driver, scorer, baseline/history
   I/O, comparator), frozen `reproduce_scenarios.jsonl` (~12 scenarios incl.
   one known-miss), `contig reproduce-guard` CLI, CI step, honest-scope
   roadmap/CHANGELOG notes.
2. **`capture-promote`** (M): `ReproduceCase` model + capture append in the
   `contig reproduce` CLI, `pending_reproduce_corpus.jsonl`,
   `contig reproduce-case-promote` (+ `--confirm-all`), golden corpus,
   promote auto-snapshot, round-trip + anti-tautology pins.
