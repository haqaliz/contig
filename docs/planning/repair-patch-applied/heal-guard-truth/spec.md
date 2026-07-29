# Aspect spec — `heal-guard-truth`

The aspect that touches a **frozen baseline**. It ships as its own commit so a changed
recorded metric is reviewable in isolation.

## Problem slice

Two connected defects:

1. `heal-guard` cannot see the new field at all, so nothing guards `patch_applied` through the
   **real** self-heal loop — only unit tests cover it (R7).
2. `heal.py:153` computes `recovered = RunSummary.from_events(record.events).succeeded`, which
   is **event-derived**. A scenario that is green from attempt 1 therefore reports
   `recovered=True` although nothing was recovered. The qc-anomaly slice **disclosed this as
   an artifact rather than fixing it** (`CAPABILITY_ROADMAP.md:1128-1132`); `patch_applied`
   makes the honest definition available for the first time (R8).

## In scope

- **R7** — an **optional** `expected_patch_applied` field on `HealScenario` (`models.py:565`
  neighbourhood), populated across the 9 scenarios in `src/contig/data/heal_scenarios.jsonl`,
  and checked in the driver's `divergence` list alongside class/recovered/outcome.
- **R8** — redefine `recovered` in `heal.py` to `succeeded AND any(step.patch_applied)`, and
  correct the one scenario whose expectation changes.
- The deliberate `contig heal-guard --update-baseline` refreeze.

## The expected values (verified against the current frozen set)

| Scenario | class | `expected_recovered` | `expected_patch_applied` |
|---|---|---|---|
| `oom-heal` | oom | True (unchanged) | true |
| `time-limit-heal` | time_limit | True (unchanged) | true |
| `missing-index-buildable-heal` | missing_index | True (unchanged) | true |
| `missing-index-unresolvable-giveup` | missing_index | False (unchanged) | false |
| `tool-crash-giveup` | tool_crash | False (unchanged) | false |
| `approval-approved-heal` | bad_param | True (unchanged) | true |
| `approval-timeout-giveup` | missing_index | False (unchanged) | false |
| `no-progress-heal` | no_progress | True (unchanged) | true |
| **`qc-anomaly-verdict-flagged`** | qc_anomaly | **True → False** | false |

**Exactly one expectation changes**, and that change is the correction, not a workaround.

## What moves, and what must not

- `outcome_match_rate` **stays 1.0** (9/9). `recovered` feeds `divergence` → `matched`
  (`heal.py:168-171`), so it only stays 1.0 *because* `expected_recovered` is corrected in the
  same commit. **If it drops, stop — something else is wrong.**
- `recovery_rate` moves **0.667 → 0.556** (6/9 → 5/9). Informational-only, never guarded
  (`regressed` is computed from `outcome_match_rate` alone, `heal.py:350`).
- `corpus_sha` changes — verified: `corpus_sha = sha256_file(scenarios_path)` (`cli.py:2725`)
  hashes the **file bytes**, so editing the jsonl moves it and triggers the loud mismatch
  warning. One refreeze covers both R7 and R8.
- `covered_classes` stays 7. `eval-guard` is **untouched** (0.923) — the detector corpus
  contains no `RepairStep`.

## Out of scope

Any change to `outcome_match_rate`'s definition, to the guarded-vs-informational split, to
`eval_history`/`snapshot_history`, or to the `qc_anomaly` diagnosis path itself.

## Acceptance criteria (testable)

1. A scenario declaring `expected_patch_applied` that the loop contradicts produces a
   `divergence` entry naming the field, and `matched` is False.
2. `expected_patch_applied` is **optional** — the 8 pre-existing scenarios must still parse
   and behave identically if the field is absent (mirrors how the qc-anomaly slice added its
   optional `HealScenario` field).
3. `recovered` is True only when the run succeeded **and** some step was applied; the
   qc-anomaly scenario reports False.
4. `uv run contig heal-guard` reports `outcome_match_rate` 1.0 over 9 scenarios and
   `recovery_rate` 0.556 after the refreeze.
5. `uv run contig eval-guard` unmoved at 0.923.
6. Full `uv run pytest` green, including `tests/test_heal_scenarios.py` and
   `tests/test_heal_guard.py`.

## Dependencies and sequencing

Depends on `patch-applied-field`. Independent of the other two siblings.

**Commit discipline:** the code change and the `--update-baseline` refreeze are **separate
commits**, and the refreeze message must state the redefinition and that the sixth
`recovery_rate` trend point is **not comparable** to the prior five (0.571 ×3, 0.625, 0.667),
all of which were computed under the old definition.

## Risks specific to this aspect

- Refreezing without correcting `expected_recovered` would hide a real drop in a guarded
  number behind a baseline update. Correct the scenario file **first**, verify 1.0, then refreeze.
- `heal_history.jsonl` is **append-only** and must never be rewritten. Do not "fix" the
  historical `recovery_rate` values to match the new definition.
