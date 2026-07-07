# Understanding: self-heal-eval-guard (Phase 2 deep dig)

## What the work is really asking

Add a **held-out benchmark + regression guard for the whole self-heal loop's
recovery rate** — the loop-level analogue of the shipped detector `contig
eval-guard` (v0.17.0). Today we guard whether Contig *diagnoses* right (detector
classification accuracy on a frozen `FailureCase` corpus). Nothing guards whether
the loop actually *recovers* (detect → diagnose → patch → retry → healed). Recovery
rate is the Phase 1→2 gate (`docs/ROADMAP.md:109`, "≥70% unattended completion")
and the Phase 3 flywheel target (`docs/ROADMAP.md:161`), yet it is unmeasured and
unguarded. This closes moat #2's biggest measurement gap.

Deliverable: a `contig heal-guard` command that runs a frozen set of synthetic
injected-failure scenarios through `self_heal_run` (via its injectable seams),
scores overall recovery rate, compares to a committed baseline, fails the build on
regression, and refreezes with `--update-baseline`. Wired into CI after the pytest
step, exactly as `eval-guard` is.

## Affected areas (all verified by the Phase-2 map)

- `src/contig/self_heal.py:793` — `self_heal_run(*, executor=default_executor,
  index_builder=default_index_builder, poll=_poll_approval_file, auto_approve=…,
  resource_ceiling=…, propose=…, max_attempts=…, assay=…, …)`. **All the seams a
  benchmark needs are already injectable.** No change needed here.
- `src/contig/runner.py:215,220,236,250` — `Executor = Callable[[list[str], Path],
  int]` and `IndexBuilder = Callable[[list[str], Path], int]`; the scripted-seam
  contract (write `trace_path` + sibling `run.log`, return an int exit code).
- `src/contig/holdout.py` — `default_holdout_path`, `default_baseline_path`,
  `save_baseline`, `load_baseline`, `compare_to_baseline`. Detector-scoped today;
  the guard-compare logic (delta, regressed/improved tolerance band, sha/detector
  mismatch, pure-function + CLI-decides split) is the template to mirror.
- `src/contig/models.py` — `EvalSnapshot` (:397), `HoldoutGuardResult` (:417),
  `DetectorEvalReport` (:387), `ClassScore` (:377), `FailureCase` (:358),
  `FailureClass` (:208, 16-member `Literal`), `RunRecord` (:261, the
  `self_heal_run` return; `.verdict`, `.repair_history[-1].outcome`), `RepairStep`
  (:251), `RunSummary.from_events(...).succeeded`.
- `src/contig/cli.py:1579` — `eval-guard` command (the CLI shape, flags, exit
  codes, print lines to mirror for `heal-guard`).
- `src/contig/data/` — `detector_corpus_holdout.jsonl` (12 cases),
  `holdout_baseline.json` (single pretty `EvalSnapshot`). New siblings needed for
  the heal set + heal baseline.
- `.github/workflows/ci.yml:23` — add `- run: uv run contig heal-guard` after the
  `eval-guard` step.
- **No dashboard surface** — `eval-guard`/`holdout` have none (grep of `dashboard/`
  empty); this slice is CLI + CI only, matching the pattern.

## The crux (the one real design decision)

**A heal scenario is NOT a `FailureCase`.** `FailureCase` is a single static
snapshot (`events` + `log_text` → `expected_class`) — the detector's input and
label — fully serializable to JSONL and sha-able. A heal scenario is a **multi-attempt
fail-then-succeed script plus seam configuration plus an expected terminal
outcome**, and `self_heal_run` returns a `RunRecord` with **no top-level status**
(recovery is read as `RunSummary.from_events(record.events).succeeded`; give-up as
`record.verdict == "fail"` + the last `RepairStep.outcome`).

You cannot put a Python callable (the scripted executor) into frozen JSONL. So the
"frozen held-out set" must be a **declarative scenario spec** (JSONL, sha-able) that
a **generic scenario driver** interprets at runtime into a scripted `executor`/
`index_builder` and the right seam flags. A scenario record must express, at minimum:
per-attempt outcomes (trace status + exit code + `log_text`, in order), seam config
(`auto_approve`, poll decision approve/reject/timeout, `resource_ceiling` to force a
ceiling give-up, index-builder success/failure), and the expected result (`recovered:
bool`, optionally expected terminal `outcome` and `failure_class`). This keeps the
set frozen, hashable, honest, and extensible — mirroring the detector corpus.

## Honesty constraints (must hold — from the card + CLAUDE.md)

- **Synthetic, not field.** Scenarios are synthetic injected failures via the seam;
  label `source="holdout:synthetic"` and never present the number as a real-world
  recovery rate.
- **Partial coverage, stated.** Only failure kinds whose seams are injectable in CI
  can be exercised; enumerate the covered `FailureClass`es and document the deferred
  ones. The committed baseline is an honest partial-coverage number (as `eval-guard`
  shipped at 0.833 with two structurally-unreachable classes).
- **Reachable classes only.** `qc_anomaly` and `no_progress` are structurally
  unreachable by `diagnose_failure` today (`CHANGELOG.md:182`) — a heal scenario
  cannot exercise them; don't pretend to.

## Layer-2 / moat check

Dead-center Layer 2 (self-heal + verify + the compounding eval flywheel). No Layer-1
authoring, no raw-read egress (pure local synthetic fixtures, no nf-core run in CI),
no over-claiming (honest synthetic + partial-coverage labels). Gets better as base
models improve (a better diagnoser/patcher raises the number; a regression drops it).

## Open questions for the PRD / interview

1. **New models vs bend `EvalSnapshot`.** `EvalSnapshot.accuracy`/`detector`/
   `per_class: ClassScore(precision, recall)` are detector-named and don't fit
   recovered/total counts. Lean: introduce a dedicated `HealSnapshot` +
   `HealGuardResult` (mirroring `EvalSnapshot`/`HoldoutGuardResult`) rather than
   overload the detector models. Confirm.
2. **Scenario schema + generic driver** as above — confirm the declarative-JSONL
   approach over hardcoded Python scenarios.
3. **Covered `FailureClass` set for slice 1** — proposed: `oom` and `time_limit`
   (resource patch → succeed), `missing_index` (build → succeed, and unresolvable →
   gave-up), `tool_crash` (gave-up), plus at least one approval-gated path
   (approved-and-retried vs approval-timed-out). Confirm scope; enumerate deferred.
4. **Metric definition** — overall `recovery_rate = recovered / total`, with a
   per-class recovered/total breakdown; regression = rate drops below baseline minus
   tolerance. Confirm.
