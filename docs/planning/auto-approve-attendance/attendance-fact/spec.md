# Aspect spec — `attendance-fact`

**Feature:** `auto-approve-attendance` · **PRD:** `../prd.md` (approved 2026-09-06)

**Why one aspect.** The slice is a single causal chain — persist a fact, read it, use it,
report it — and every proposed split leaves a phase that cannot be validated on its own
(a persisted field nothing reads; a rule with no fact to read). It is decomposed into
**phases** in `plan_20260906.md` instead, one of which (R4) is genuinely independent and
lands first as its own commit.

## Problem slice

A run bundle cannot say whether a human was in the loop, so `contig repair-stats` either
excludes runs from the Phase-2 gate metric (`docs/ROADMAP.md:109`) or, worse, silently
counts a human-approved index build as an unattended completion.

## In scope

- `LaunchManifest.auto_approve: bool | None`, written at launch, never replayed (R1, R2).
- A tolerant `launch.json` loader; the fact carried on `LoadedRun` (R3).
- `chose_and_retried` corrected to strictly attended (R4) — **independent**, lands first.
- Attendance derived from the flag for every gated literal, with the literal winning on a
  contradictory bundle (R5, R5a) and `None` meaning unknown (R6).
- CLI: attribute the two causes of `attendance_unknown`; drop the now-false "never
  recorded" wording (R6a, R7).

## Out of scope

Everything in the PRD's Out of Scope, notably any `RunRecord` or signed-payload change,
`--auto-approve` on `rerun`/`resume`, and dashboard surfaces.

## Acceptance criteria

The PRD's AC#1-16 in full. AC#12's real-corpus half is a **manual gate**, not a test.

## Dependencies and sequencing

No external dependency, no new package. Phase 0 (R4) and Phase 1 (persist) are mutually
independent; Phase 2 depends on 1; Phase 3 on 0 and 2; Phase 4 on 3.

## Risks specific to this aspect

- R2 is a convention, not a mechanism — AC#4 is its only tripwire.
- R6 widens the unknown bucket for legacy bundles; a no-op today (AC#12) but it makes the
  rate *less* computable on a corpus with many legacy gated steps.
