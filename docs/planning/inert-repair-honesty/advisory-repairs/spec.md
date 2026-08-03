# Aspect spec — advisory-repairs

Parent PRD: [`../prd.md`](../prd.md). Single aspect, phased plan (house pattern: the
`catalog-coverage` slice used the same shape).

## Problem slice

Five repair strategies propose operations nothing performs, and the loop records enactment and
recovery for all five. Resolve every one of them: four become **advisories** (guidance for a
human, never claimed as enacted), one gets a **genuine enactment** (a real, injected-clock
wait).

## User outcome

A human at the approval gate is never shown a machine operation Contig will not perform, and no
surface reports a repair Contig did not make. A transient Docker-daemon blip is actually waited
out instead of being retried instantly and failing identically.

## In scope

- New `Patch.kind = "advisory"` (`models.py:300`) — enum member only, **no new field**.
- `disk_full`, `permission_denied`, `conda_solve_failed`, `platform_unsupported` → advisory;
  their inert operations removed.
- `advisory_acknowledged_and_retried` outcome literal; `patch_applied False` by construction
  via `continue_=False`.
- `--auto-approve` skips advisories (**R-Open-0 resolution (a)**, approved 2026-08-03).
- `container_unavailable` → real bounded wait through an injected `Sleeper` seam threaded
  through `self_heal_run` **and** `heal.py`.
- Gate payload stops carrying an advisory `operation`; both dashboard repair surfaces updated
  together; `OUTCOME_META` 18 → 19 with its pinned contract satisfied.
- Retire/replace the inertness guard; correct the two false statements; `heal-guard` scenarios
  for the four reachable classes + deliberate baseline refreeze; docs.

## Out of scope

Enacting the four rejected operations; any `detect.py` change; the `destructive` risk-tier gap;
the `read_task_errors` work-dir bug; any new `Patch`/`RepairStep` field.

## Acceptance criteria

1. Each advisory class: advisory patch, no machine operation; approval → `patch_applied False`,
   `recovered False`, `advisory_acknowledged_and_retried`.
2. `--auto-approve` + advisory → no retry claimed; guidance recorded.
3. `container_unavailable` retry waits `wait_seconds` via injected clock (never really slept).
4. Pre-change signed record still verifies (no fifth signature break).
5. `eval-guard` unmoved at 92.3%; `heal-guard` outcome-match 1.0, `covered_classes` 11 → 15.
6. Inertness guard replaced by one pinning the new contract.

## Dependencies & sequencing

Engine core (model + proposer + apply) must land before surfaces, scenarios, or the guard
rewrite. The baseline refreeze is last and is a deliberate act.

## Open questions

- R-Open-1: advisory `operation` dict contents (`operation` is a required
  `dict[str, object]`).
- R-Open-2: `platform_unsupported` stays `heal-guard`-uncovered — confirm and record the
  reason (`detect.py:353` needs `exit is None`; `AttemptSpec.exit` is a required `int`).
- R-Open-3: `approval-gate.tsx:163` copy is misleading for an advisory.
