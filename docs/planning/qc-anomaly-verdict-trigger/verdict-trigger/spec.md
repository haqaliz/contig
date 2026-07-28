# Aspect spec — `verdict-trigger`

Parent PRD: [`../prd.md`](../prd.md) · Single aspect for this slice.

## Problem slice

`self_heal_run` only ever diagnoses a **non-zero exit**: `diagnose_failure` is called from the
one `except PipelineExecutionError` branch (`self_heal.py:993`). A run that finishes with every
task green and whose QC then reduces to **FAIL** returns through `self_heal.py:984` straight into
`_finalize` at `:985` — undiagnosed, absent from `repair_history`, and absent from the corpus.
`qc_anomaly` is the `FailureClass` literal that names this and that nothing can produce.

**User outcome:** the same verdict, the same exit code, the same lifecycle event — plus one
diagnosed `qc_anomaly` step naming the failing checks and stating that no repair was attempted
because none can work, and one pending-corpus case.

## In scope

1. The R1 trigger in `self_heal_run`, on the success path only.
2. A synthesized `Diagnosis(failure_class="qc_anomaly")` — `detect.py` untouched.
3. A new outcome literal `qc_verdict_flagged` as a shared module constant.
4. Pending-corpus capture for the QC-FAIL run.
5. One frozen `heal-guard` scenario driving the **real** `_discover_qc` to FAIL, plus the
   minimal harness change to write its artifact, plus deliberate baseline refreeze.
6. Doc corrections: `cli.py` heal-guard docstring, `CAPABILITY_ROADMAP.md`'s stale
   "QC runs at `_finalize`" rationale, `CHANGELOG.md`, `FEATURES.md`.

## Out of scope

Everything in the PRD's *Out of Scope*, plus specifically: no `detect.py` needle branch, no
`repair.py` branch, no `eval-guard`/`holdout_baseline.json` movement, no committed
detector-corpus case, no verdict/band/threshold change, no flag, no dashboard work.

## Acceptance criteria (all testable)

| # | Criterion |
|---|---|
| A1 | A green run (all events COMPLETED) whose `qc_results` reduce to `fail` yields exactly one `RepairStep` with `failure_class="qc_anomaly"`, `patch=None`, `outcome="qc_verdict_flagged"` |
| A2 | A run with a **FAILED task event** and returncode 0 does **not** produce `qc_anomaly` (condition 1 is load-bearing) |
| A3 | Empty `qc_results` (→ `unverified`) produces **no** `RepairStep` — silent skip |
| A4 | `warn`, `pass`, and `unverified` verdicts produce **no** `RepairStep` |
| A5 | A verdict that is FAIL **only** because of an `informational=True` check produces **no** `RepairStep` (rides `overall_verdict`'s existing filter) |
| A6 | Exit code for a QC-only FAIL is **0** without `--fail-on-verdict` and **1** with it — unchanged both ways |
| A7 | The lifecycle event stays `finished`, not `failed` |
| A8 | `record.verdict` is byte-identical to today on every path |
| A9 | `_finalize` is called exactly once, and stays terminal |
| A10 | The trigger fires **at most once** per run (no loop) |
| A11 | A pending-corpus `FailureCase` is written for the QC-FAIL run, labelled `qc_anomaly` |
| A12 | `evidence` names the failing check(s); `detail` carries the count, the check names, and the no-repair-attempted reason |
| A13 | `propose_patches` still has **no** `qc_anomaly` branch (pinned, so nobody adds one without revisiting R4) |
| A14 | The frozen `qc-anomaly-verdict-flagged` scenario replays through the real loop: `diagnosed_class="qc_anomaly"`, `actual_outcome="qc_verdict_flagged"`, `matched=True` |
| A15 | `heal-guard` reports `covered_classes` 7 and `outcome_match_rate` **1.0** |
| A16 | `eval-guard` still reports **0.923** — unchanged, asserted rather than assumed |
| A17 | The real `runs/variant-bad`-shaped record (green sarek, `ts_tv_ratio` FAIL) trips the trigger — a regression test from a real bundle shape, not a synthetic one |

## Dependencies & sequencing

No blocking dependencies. Phase order in the plan is: pre-flight impact checks → trigger →
capture → heal coverage → docs. The heal scenario depends on the outcome constant existing.

## Aspect-specific risks

- **`recovery_rate` artifact** (see plan Phase 3, D8): our scenario is green from attempt 1, so
  the driver computes `recovered=True` and `expected_recovered` must be `true` — inflating
  `recovery_rate` 5/8 → 6/9 for a scenario that recovered nothing. Disclosed, not fixed.
- **O2**: a downstream consumer may assume non-empty `repair_history` implies a failed run.
- **Gap 3** from the PRD critique: `confidence = 1.0` is a new extremum on a shared semantic.
