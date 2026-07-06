# Aspect spec — `sizing`

The single aspect of `peak-rss-resource-scaling`: size the OOM memory retry to observed
peak RSS with a full fallback ladder. (Parent PRD: `../prd.md`.)

## Problem slice / outcome

An OOM self-heal retry is sized to the failed task's observed peak memory instead of a
blind ×2, converging faster within the bounded retry budget and wasting less memory —
while never regressing when no usable peak is available.

## In scope

- A pure sizing helper `(events, resource_usage, factor) → PeakSizing(target_gb|None, tier, observed_peak_mb)`.
- **Two-tier** ladder (corrected from three during impl): OOM'd task's own positive peak →
  `None` (blind). The same-`process` sibling rung was **cut** — unreachable because the
  parser sets `process == name` (see the risk note); deferred as its own slice.
- Thread the sized target into `apply_patch` (memory branch only), preserving ceiling
  clamp + never-shrink.
- Telemetry (observed peak, tier, sized-vs-current) into `RepairStep.detail` at the OOM
  safe-path site.

## Out of scope

Walltime/`time_limit` sizing; snakemake; `FailureCase`/corpus schema; `peak_vmem`; any
verdict/exit-code/`FailureClass` change.

## Acceptance criteria (testable)

1. Helper returns tier `oom_task` (max peak among `exit==137` rows with peak>0), `sibling`
   (max same-`process` positive peak when the OOM'd row's own peak is 0/absent), or
   `unavailable` (→ None) — incl. multi-task OOM → max, and no-`exit==137` → unavailable.
2. `target_gb = ceil(peak_mb/1024 × 1.5)`, binary GB.
3. `apply_patch` with a sized target: memory = `min(ceiling, max(target, current))`;
   without: unchanged blind ×2; sub-current target → never-shrink holds `current`;
   over-ceiling → clamped.
4. End-to-end heal: partial trace with a high peak on the OOM'd row → one retry lands at
   the sized memory (not ×2), run reaches its verdict; `RepairStep.detail` names the
   observed peak + tier. A trace with no usable peak → blind ×2 (regression guard).
5. `gave_up_at_ceiling`, `max_attempts`, and the time-branch behavior unchanged.

## Dependencies / sequencing

Helper (Phase 1) → `apply_patch` seam (Phase 2) → heal-site wiring + integration
(Phase 3) → changelog/refactor (Phase 4). No new deps.

## Aspect-specific risk (resolved during impl)

The `TaskEvent`↔`TaskResource` **join key** turned out exact — both set `process`/`name`
from the same trace `name` column (`events.py:91/95,127/131`). That same fact is what made
the **sibling rung unreachable** (`process` can never diverge from `name`), so tier b was
cut. Tier a (own-task peak) joins reliably. The residual risk is empirical, outside the
code: whether Nextflow records a usable `peak_rss` on a signal-killed row — if not, sizing
falls through to blind (the honest, non-regressing default).
