# Aspect spec — sizing (walltime-informed self-heal)

The sole aspect of `walltime-resource-scaling`. Mirrors the shipped memory-sizing aspect
(`peak-rss-resource-scaling/sizing`), with one intentional asymmetry: **floor-at-blind**.

## Problem slice & user outcome

A `time_limit` self-heal retries with a blind `time × 2`. Size it instead from the run's
own observed `realtime`, but **never below** blind `× 2` (the observation is a censored
lower bound). Outcome: unattended runs recover a mis-labeled long-pole task in one round
in the tail case; identical to today otherwise; every heal emits field telemetry.

## In scope

- Pure sizer `realtime_informed_time_h` in `src/contig/resource_sizing.py` (+ `TimeSizing`
  type + `WALLTIME_SAFETY_FACTOR` constant).
- `apply_patch` gains `observed_target_h` with **floor-at-blind** in the time branch.
- `_time_limit_sizing` wiring + heal-site dispatch + `RepairStep.detail` telemetry.
- Tests at all three layers (pure, seam, integration), written first.

## Out of scope

Memory/peak-RSS path (untouched); sibling-rescue tier (parser `process==name` block);
snakemake; any verdict/exit-code/`FailureClass`/model/parser change; factor calibration.

## Acceptance criteria (testable)

1. `realtime_informed_time_h`: max `realtime_sec>0` over `usage` → `ceil(max/3600×factor)`;
   no usable row → `(None,"unavailable",None)`; `factor` default = `WALLTIME_SAFETY_FACTOR`.
2. `apply_patch(observed_target_h=h)` time branch: applied time = `max(min(max(h,
   current×mult), ceiling), current)`; i.e. **never below blind `× 2`**, clamped to 72h,
   never shrunk. `observed_target_h=None` reproduces today's blind bump byte-for-byte.
   Memory branch unaffected; both overrides honored independently.
3. Heal loop: a tail trace (observed realtime > current limit) sizes the retry above blind;
   a censored trace (realtime ≈ limit) ties blind exactly; a trace-less / `realtime`-absent
   run falls back to blind. `RepairStep.detail` records the observed realtime (seconds) and
   the applied target on every walltime heal; the unavailable path names the fallback.
4. `test_gives_up_at_time_ceiling` and all memory-sizing tests pass unchanged.

## Dependencies & sequencing

Phase 1 (sizer) and Phase 2 (`apply_patch` kwarg) are independent → parallelizable. Phase 3
(wiring + integration) depends on both. Phase 4 (changelog/docs) depends on Phase 3.

## Aspect-specific risks

- Detail accuracy under floor/clamp: build the telemetry so it reflects the **applied**
  time (post-floor), not the raw sized value, so a floored heal doesn't misreport. Pin with
  the integration test.
- `realtime` unit is **seconds** in the trace but **hours** in config — convert `/3600`.
