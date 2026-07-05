# Task 3 report — Phase D: freeze committed baseline + record C6 slice-1 as shipped

Date: 2026-07-05 · Worktree: `.claude/worktrees/feat-eval-holdout-guard`
Plan: `docs/planning/eval-holdout-guard/holdout-guard/plan_20260705.md` (Phase D only)

## Scope

Phase D only: data + docs. No code behavior touched. Phases A–C (corpus, holdout.py,
`HoldoutGuardResult`, `contig eval-guard`) were already merged (commits `228e3d6`,
`ce8cfa0`, `c9a7411`).

## 1. Frozen committed baseline

Confirmed the accuracy before freezing (read-only check, no baseline written yet):

```
$ uv run python -c "from contig.corpus import evaluate_detector, load_corpus; \
  from contig.holdout import default_holdout_path; \
  r=evaluate_detector(load_corpus(default_holdout_path())); \
  print('accuracy', r.accuracy); \
  print('mismatches', [(m.case_id, m.expected, m.predicted) for m in r.mismatches])"
accuracy 0.8333333333333334
mismatches [('holdout-qc-anomaly-1', 'qc_anomaly', 'tool_crash'), ('holdout-no-progress-1', 'no_progress', 'tool_crash')]
```

This matched the expected honest 10/12 = 0.8333 (`qc_anomaly` and `no_progress`
structurally unreachable by `diagnose_failure` today), so I proceeded without pausing
for human confirmation (task instructions said to ask only if accuracy was NOT ≈0.833).

Froze the baseline at the default path (no `--baseline` override):

```
$ uv run contig eval-guard --update-baseline
Baseline updated: accuracy 83.3% over 12 held-out cases (detector=rules, sha ba791e75e7b8...)
```

`src/contig/data/holdout_baseline.json` (generated, then `git add`ed) — a single
`EvalSnapshot` JSON object:

- `corpus_size`: 12
- `corpus_sha`: `ba791e75e7b8d44fb708be26ff97b9abc98a5c56a1719c8fc6acfe28dee7edea`
- `accuracy`: `0.8333333333333334`
- `detector`: `"rules"`
- `contig_version`: `"0.16.0"`
- `per_class`: 12 classes, each `support=1`; `qc_anomaly` and `no_progress` have
  `predicted=0, correct=0, recall=0.0` (both misclassified as `tool_crash`, which
  shows `predicted=3, correct=1, precision=0.33`).

Verified the guard passes against the freshly committed baseline:

```
$ uv run contig eval-guard
Guard: accuracy 83.3% vs baseline 83.3% (delta +0.0pp) over 12 held-out cases [rules]
  MISS holdout-qc-anomaly-1: expected qc_anomaly, predicted tool_crash
  MISS holdout-no-progress-1: expected no_progress, predicted tool_crash
Guard PASS: accuracy 83.3% ≥ baseline 83.3%.
$ echo $?
0
```

`git add src/contig/data/holdout_baseline.json` staged (94 insertions, new file).

## 2. CHANGELOG.md

Added an `### Added` entry under `## [Unreleased]` (before the `## [0.16.0]` section),
matching the existing entry voice (bold lead phrase, backtick-quoted paths/flags,
explicit honest-scope/deferred callouts, e.g. mirroring the bwa-mem2 v0.11.0 entry's
"Deferred (...)" pattern). Key content: frozen `detector_corpus_holdout.jsonl` (12
cases), `contig eval-guard`, fail-on-drop vs `holdout_baseline.json`,
`--update-baseline`, sha/detector-mismatch warnings, improvement nudge, the honest
83.3% (10/12) baseline with the two structurally-unreachable classes named, and the
explicit deferred scope (unlabeled C1/C3 signals, repair-loop accuracy, CI wiring).

Before: `## [Unreleased]` had no subsections (blank, directly followed by `## [0.16.0]`).
After: `## [Unreleased]` now has one `### Added` bullet (see diff below, +28 lines).

```diff
 ## [Unreleased]
 
+### Added
+
+- **Held-out regression guard for the diagnosis detector** (capability C6, eval
+  flywheel — slice 1). A new frozen `src/contig/data/detector_corpus_holdout.jsonl`
+  (12 newly authored `FailureCase`s, `source="holdout:synthetic"`, disjoint `case_id`s
+  from the training corpus) is scored by a new `contig eval-guard` command, ...
+  [full text in CHANGELOG.md]
+
 ## [0.16.0] - 2026-07-05
```

## 3. docs/technical/CAPABILITY_ROADMAP.md §C6

Inserted a **"Slice 1 — SHIPPED (Unreleased)"** paragraph immediately after the
existing "Acceptance (test-first)" line and before "Eval data captured:", describing
what shipped, the honest 0.833 (10/12) number with the two unreachable classes named,
"Honest scope, unchanged from the PRD" (labeled failure-class corpus only), and
"Pending follow-on slices" (folding C1/C3 unlabeled signals + repair-loop accuracy into
one number — explicitly noting the roadmap's own "fold C1–C5 into one number" framing
is *not yet built*; a held-out-accuracy trend mirroring `eval-detector --history`; CI
wiring).

Also updated the "Sequencing summary" table's C6 row (`Window` column) from `M6` to
`M6 (held-out set + regression-guard slice 1 SHIPPED, Unreleased — honestly 0.833/10:12,
two classes structurally unreachable; folding C1/C3 signals + repair-loop accuracy + CI
wiring pending)`, consistent with how other rows (C1, C2, C4, C5) record shipped
sub-slices inline.

Left "fold C1–C5 into one number" and the held-out-accuracy-trend items as pending
follow-ons — did not mark them shipped.

## 4. FEATURES.md

The C6 row in the "engine capability track" table (previously: `M6` window, "Fold C1
to C5 outcomes into a measured, regression-guarded improvement loop" — asserting an
unbuilt aspirational state) was updated to:

- Window column: `**Slice 1 shipped (Unreleased)** — held-out set + regression guard;
  folding C1/C3 + repair-loop accuracy + CI wiring pending`
- "What it adds" column: rewritten to describe what actually shipped (frozen 12-case
  held-out corpus, `contig eval-guard`, committed baseline, `--update-baseline`,
  mismatch warnings, improvement nudge), the honest 0.833 (10/12) figure with the two
  unreachable classes named as headroom, and the scope line (labeled failure-class
  corpus only; C1/C3 unlabeled signals and whole-loop repair accuracy deferred).

This was a genuine change, not a no-op: the prior text implied C6 was entirely future
work with no shipped component, which was no longer accurate.

## Suite result

```
$ uv run pytest
1092 passed, 1 skipped in 10.97s
```

Matches the stated baseline exactly (1092 passed, 1 skipped) — no test count drift,
confirming Phase D touched no code paths that affect existing tests (only added a
generated data file + prose docs).

## Exact commands run (chronological)

```
cd /Users/aliz/dev/at/contig/.claude/worktrees/feat-eval-holdout-guard
uv run pytest -q                      # baseline check: 1092 passed, 1 skipped
uv run python -c "... accuracy check before freezing ..."   # 0.8333333333333334
uv run contig eval-guard --update-baseline
uv run contig eval-guard              # exit 0, Guard PASS
git add src/contig/data/holdout_baseline.json
# edited CHANGELOG.md, docs/technical/CAPABILITY_ROADMAP.md, FEATURES.md
uv run pytest                          # 1092 passed, 1 skipped (post-doc-edit re-check)
```

## Concerns / notes

- `docs/planning/eval-holdout-guard/holdout-guard/task-1-report.md` is untracked
  (leftover from an earlier task run, never committed) and was **not** touched or
  added by this task — left as-is, out of scope for Phase D.
- No CI wiring was done (Phase E explicitly out of scope per the task brief).
- No code behavior was changed; the only non-doc file touched is the generated
  `holdout_baseline.json`, as instructed.
- The baseline's `contig_version` field reads `0.16.0` (the version at HEAD in this
  worktree) — this is expected and matches `pyproject.toml`/the CHANGELOG's latest
  released version; the `[Unreleased]` CHANGELOG entry sits above it as usual.
