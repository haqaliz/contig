# Understanding — holdout-accuracy-trend (Phase 2 dig)

## What the work is really asking

Give `contig eval-guard` (held-out **detector accuracy**) and `contig heal-guard`
(self-heal **outcome-match rate**) the same over-time trend capability that
`contig eval-detector` already has via `--snapshot` / `--history`. Today both guards
compute a number and compare it to a single frozen baseline (pass/fail the CI build),
but they keep **no history**, so there is no visible trajectory of "are we getting
better over corpus/detector versions." This slice adds that trajectory — the durable
instrument for moat #2 (compounding evaluation data) and CLAUDE.md #3 (better base
model → visibly rising held-out trend).

## Affected areas (file:line grounded)

- **`src/contig/cli.py`**
  - `eval-guard` cmd: `cli.py:1870-1983`. Has `--update-baseline`, `--json`; **no
    `--snapshot`/`--history`**. Produces `DetectorEvalReport` (`evaluate_detector`) +
    `HoldoutGuardResult` (`compare_to_baseline`). `--update-baseline` already builds an
    `EvalSnapshot` via `snapshot_from_report(...)` and `save_baseline(...)`.
  - `heal-guard` cmd: `cli.py:1986-2101`. Same shape; produces `HealEvalReport`
    (`evaluate_heal`) + `HealGuardResult`. `--update-baseline` builds a `HealSnapshot`
    via `snapshot_from_heal_report(...)`.
  - `eval-detector --snapshot/--history`: `cli.py:1799-1867` — **the precedent to
    mirror**. `--snapshot` → `append_snapshot(snapshot_from_report(...), history_path)`;
    `--history` → `load_history` + a text render (`accuracy over time`, one line/snap).
    Version `_pkg_version("contig")` (`cli.py:18`), time `datetime.now(timezone.utc)
    .isoformat()` inlined at call site (no shared helper).
- **`src/contig/eval_history.py`** — `default_history_path()` → `data/eval_history.jsonl`;
  `append_snapshot()` (JSONL append), `load_history()` (per-line `EvalSnapshot`
  validate), `snapshot_from_report()` (pure projection). **EvalSnapshot-only** today.
- **`src/contig/holdout.py`** — `default_holdout_path()`, `default_baseline_path()`,
  `save_baseline`/`load_baseline` (pretty JSON, `EvalSnapshot`), `compare_to_baseline`.
- **`src/contig/heal.py`** — `evaluate_heal`, `run_heal_scenario` (drives the REAL
  `self_heal_run`), `save_heal_baseline`/`load_heal_baseline` (`HealSnapshot`),
  `compare_heal_to_baseline`, `snapshot_from_heal_report`, default path helpers.
- **`src/contig/models.py`** — `EvalSnapshot` (478-495; `timestamp, corpus_size,
  corpus_sha, accuracy, per_class: ClassScore, contig_version, detector`);
  `HealSnapshot` (597-615; `timestamp, scenario_count, corpus_sha, outcome_match_rate,
  recovery_rate, per_class: HealClassScore, covered_classes, contig_version`) — its
  docstring literally says "there is no history file … `--history` is explicitly
  deferred." Guard results `HoldoutGuardResult` (498-521), `HealGuardResult` (618-636).
- **`.github/workflows/ci.yml:23,27`** — bare `uv run contig eval-guard` / `heal-guard`
  in the `engine` job (no `--snapshot`).
- **Tests** — `tests/test_eval_history.py` (trend precedent, `tmp_path`, literal
  `timestamp=`), `tests/test_eval_holdout.py`, `tests/test_heal_guard.py`,
  `tests/test_cli_heal_guard.py`.
- **Dashboard** (likely OUT of slice 1) — `dashboard/lib/runs.ts:894-928` reads
  `eval_history.jsonl`; `dashboard/components/eval/eval-history.tsx` renders a sparkline
  + per-version delta table. No reader for a holdout/heal trend today.

## The three decisions to settle (these become PRD resolved-decisions)

1. **Persistence trigger** — snapshots must NOT be written on every CI build (floods the
   history with identical entries, since CI runs eval-guard/heal-guard on every push).
   Options: explicit `--snapshot` flag (mirrors eval-detector), and/or append on
   `--update-baseline`. → *needs a user steer; recommendation below.*
2. **One vs two history files** — the two snapshot shapes differ, and the holdout
   `corpus_sha` ≠ the training-corpus sha already in `eval_history.jsonl`. Mixing
   conflates corpora. → **Recommend two files**: `holdout_history.jsonl` (EvalSnapshot),
   `heal_history.jsonl` (HealSnapshot). Low ambiguity.
3. **`--history` delta rendering** — brief wants "per-version deltas." eval-detector's
   *CLI* renderer shows no deltas (deltas live only in the dashboard). → **Recommend the
   new `--history` renderer prints a per-version delta column** (a small, honest
   improvement over the precedent's CLI view).

## Explicitly NOT in this slice (guardrails)

- **No C1/C3 fold-in** — folding the unlabeled concordance/plausibility signals into one
  eval number is the *blocked* half of C6's pending list (needs a labeling design).
  Trend only the two already-labeled guard metrics.
- **No Layer-1 work.** Local, deterministic, no network, no raw-read egress.
- Dashboard trend series is a **candidate follow-on**, likely deferred to keep slice 1
  to CLI + persistence + tests.

## Contradictions / risks

- No contradiction between brief and code. The brief's "reuse EvalSnapshot /
  `eval_history.py`" holds for the **holdout** trend directly; the **heal** trend needs a
  parallel HealSnapshot history writer/loader (the brief's "or a snapshot record of that
  shape" already anticipates this).
- Reproducibility/determinism: `datetime.now()` is the one non-deterministic seam; tests
  inject a literal `timestamp=` into the pure builders (existing pattern), so coverage
  stays deterministic. Version is injected the same way.
- No graphify graph exists in this repo (skill mentions it aspirationally) — mapping was
  done by direct read.
