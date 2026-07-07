# Aspect spec: heal-guard

Single aspect of the `self-heal-eval-guard` feature (the whole slice is cohesive
enough to plan as one aspect). Parent PRD: `../prd.md`.

## Problem slice & user outcome

The maintainer/CI gains one guarded number that fails the build when the self-heal
loop's end-to-end behavior drifts on a frozen synthetic set: `contig heal-guard`
runs the **real** `self_heal_run` over declarative injected-failure scenarios and
checks each still (a) diagnoses the expected `FailureClass` and (b) reaches the
declared terminal outcome (healed / gave-up + `RepairStep.outcome`).

## In scope

- New Pydantic models (`AttemptSpec`, `HealScenario`, `HealClassScore`,
  `HealScenarioResult`, `HealEvalReport`, `HealSnapshot`, `HealGuardResult`).
- New `src/contig/heal.py`: scenario driver over the real loop, `evaluate_heal`,
  guard I/O + pure `compare_heal_to_baseline` (mirrors `holdout.py`/`corpus.py`).
- Frozen `src/contig/data/heal_scenarios.jsonl` (7 Core-mix scenarios) +
  `src/contig/data/heal_baseline.json` (one pretty `HealSnapshot`).
- `contig heal-guard` CLI command mirroring `eval-guard`.
- CI step after `eval-guard`; CHANGELOG + roadmap markers + `--help` deferred list.

## Out of scope

Per PRD "Out of Scope": `--history`/shared-eval-history fold, real-run telemetry,
unreachable classes (`qc_anomaly`, `no_progress`), non-injectable classes
(`bad_param`, container/download/disk/permission, …), multi-task trace fidelity,
any dashboard surface, any Layer-1 surface.

## Acceptance criteria (testable)

- `evaluate_heal` over the shipped 7 scenarios → `outcome_match_rate == 1.0`,
  `recovery_rate == 4/7`, per-class table correct.
- Each scenario's driven result matches its declared `expected_class` +
  `expected_recovered` + `expected_outcome` through the **unstubbed** detector +
  patcher (only `executor`/`index_builder`/`poll` synthesized).
- `compare_heal_to_baseline` is pure: correct `regressed`/`improved`/`sha_mismatch`/
  `has_baseline` flags; a perturbed scenario → `regressed=True`.
- `contig heal-guard` exit 0 on the frozen set; exit 1 + named scenario on a
  perturbed/injected regression; `--update-baseline` refreezes and the plain guard
  never mutates the baseline; `--json` emits `HealGuardResult`.
- Full suite green (baseline 1176 passed, 1 skipped) + the new tests; CI step added.

## Dependencies & sequencing

Models → driver+evaluate → guard I/O+compare → frozen data+baseline → CLI → CI/docs.
Scenarios transcribe log/trace fixtures from known-passing `test_self_heal.py` cases,
so authoring them is low-risk.

## Risks specific to this aspect

Getting each declarative scenario to reproduce its declared outcome through the real
loop (esp. the buildable-index heal and the approval-approved heal) — mitigated by
transcribing from existing passing `test_self_heal.py` fixtures.
