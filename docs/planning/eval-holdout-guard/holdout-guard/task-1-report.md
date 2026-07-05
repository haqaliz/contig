# Task 1 report — holdout-guard Phase A + Phase B

Worktree: `.claude/worktrees/feat-eval-holdout-guard` · Branch: `feat/eval-holdout-guard/aliz`
Plan: `docs/planning/eval-holdout-guard/holdout-guard/plan_20260705.md` (Phases A + B only)
Spec: `docs/planning/eval-holdout-guard/holdout-guard/spec.md`

## Scope executed

Phase A (frozen held-out corpus + loader) and Phase B (baseline record + pure
comparator), strict RED → GREEN, one commit per phase. Phase C (CLI command),
Phase D (freeze committed baseline + docs), Phase E (CI wiring) were **not**
touched, per instructions.

## Files created / modified

- **Created** `src/contig/holdout.py` — `default_holdout_path()`,
  `default_baseline_path()`, `save_baseline()`, `load_baseline()`,
  `compare_to_baseline()`.
- **Created** `src/contig/data/detector_corpus_holdout.jsonl` — 12 newly
  authored synthetic `FailureCase` lines.
- **Created** `tests/test_eval_holdout.py` — 16 tests (Phase A + Phase B).
- **Modified** `src/contig/models.py` — added `HoldoutGuardResult` (new
  model, all fields as specified in the plan verbatim; no existing model
  touched).
- **Not created**: `src/contig/data/holdout_baseline.json` (deliberately
  deferred to Phase D, per instructions) and no `eval-guard` CLI command was
  added to `src/contig/cli.py`.
- No `pyproject.toml` changes — data files load at runtime via
  `Path(__file__).parent / "data" / ...` exactly like the existing
  `detector_corpus.jsonl`; no explicit data-file listing exists there to update.

## Held-out corpus: count + per-class coverage

12 cases, one per class, `case_id` prefixed `holdout-`, `source =
"holdout:synthetic"` on every case:

| class | count |
|---|---|
| oom | 1 |
| time_limit | 1 |
| missing_index | 1 |
| bad_param | 1 |
| container_pull_failed | 1 |
| tool_crash | 1 |
| qc_anomaly | 1 |
| missing_reference | 1 |
| disk_full | 1 |
| download_failed | 1 |
| permission_denied | 1 |
| no_progress | 1 |
| **total** | **12** |

All 12 case_ids are disjoint from the 23 training-corpus case_ids (verified by
`test_holdout_disjoint_from_training`).

## `rules` accuracy observed on the held-out set

**0.8333 (10/12).** The two misses are structural, not an authoring gap:

```
MISS holdout-qc-anomaly-1  qc_anomaly  -> tool_crash
MISS holdout-no-progress-1 no_progress -> tool_crash
```

Confirmed by inspection of `src/contig/detect.py`: `diagnose_failure` has **no
rule branch that ever returns `qc_anomaly` or `no_progress`** — neither string
appears anywhere in the detector's rule chain (`grep -rn "no_progress\|
qc_anomaly" src/contig/*.py` matches only the `FailureClass` literal in
`models.py`). These two labels exist in the schema for future live-repair
classes the rules detector doesn't yet implement; any case labeled with them
necessarily falls through to the generic `tool_crash`/`unknown` branches. This
matches the plan's own framing ("Aim high (near 1.0); it need not be exactly
1.0") — I iterated wording for the other 10 classes until each hit its
intended rule, and left these two honestly labeled rather than picking
different classes to inflate the number. `test_rules_detector_scores_high_on_holdout`
asserts a floor of `>= 0.7` (a sanity check against a broken authoring pass,
not the exact figure — the real number gets pinned in the Phase D baseline).

## Tests

`tests/test_eval_holdout.py`, 16 tests, all passing:

Phase A (6):
- `test_holdout_loads_and_is_nonempty`
- `test_holdout_disjoint_from_training`
- `test_holdout_source_kind`
- `test_holdout_not_a_default_of_other_commands`
- `test_holdout_case_ids_prefixed`
- `test_rules_detector_scores_high_on_holdout`

Phase B (10):
- `test_default_baseline_path_differs_from_holdout_and_history`
- `test_compare_pass`
- `test_compare_regression`
- `test_compare_improvement`
- `test_compare_tolerance_absorbs_float_noise`
- `test_compare_no_baseline`
- `test_compare_sha_and_detector_mismatch`
- `test_compare_carries_mismatches_through`
- `test_baseline_roundtrip`
- `test_worse_detector_scores_lower_than_rules_on_holdout`

## Exact command run + tail output

```
$ uv run pytest
...............................................s........................ [ 79%]
........................................................................ [ 86%]
........................................................................ [ 92%]
........................................................................ [ 99%]
........                                                                 [100%]
1087 passed, 1 skipped in 10.88s
```

(Baseline before starting: 1071 passed, 1 skipped. +6 Phase A tests, +10
Phase B tests = 1087, 1 skipped — consistent, no regressions, no other test
files touched.)

## Commits

1. `228e3d6` — `feat(holdout): add frozen held-out detector corpus + loader (C6 slice 1)`
2. `ce8cfa0` — `feat(holdout): baseline record + pure regression comparator`

Both end with `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.

## Concerns

- **Non-blocking, flagged for visibility:** the two structurally-unreachable
  classes (`qc_anomaly`, `no_progress`) cap the held-out accuracy at 10/12
  regardless of wording quality — this is a `rules`-detector capability gap,
  not a held-out-corpus defect. Whoever runs Phase D (freeze the committed
  baseline) should expect ~0.833, not ~1.0, and the CHANGELOG/roadmap copy
  written in Phase D should state this honestly rather than imply the
  detector aces all 12 classes.
- Everything else validated cleanly: leakage guard, source-kind, baseline
  round-trip, comparator semantics (pass/regression/improvement/tolerance/
  no-baseline/sha+detector-mismatch), and the worse-stub-detector check all
  pass exactly as specified in the plan. No new dependencies, no network, no
  `pyproject.toml` changes, `src/contig/data/holdout_baseline.json` was not
  created.
