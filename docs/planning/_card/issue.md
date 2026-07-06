# Card: feat / self-heal-walltime-scaling

- **Type:** feat
- **Id/slug:** self-heal-walltime-scaling
- **Owner:** aliz
- **Branch:** feat/self-heal-walltime-scaling/aliz
- **Source:** inline brief (no GitHub issue — slug work, handed off from `contig-next`)

## Brief

Ship the **symmetric walltime follow-on** to v0.19.0's peak-RSS OOM memory scaling
(capability C2, self-heal breadth). When a Nextflow task is killed for exceeding its
walltime (the `time_limit` repair), size the retry to the failed task's **observed
`realtime`** parsed from the run's own partial `trace.txt` at heal-decision time,
instead of the current blind `time × 2`.

Reuse the exact seams v0.19.0 built:
- the pure `resource_sizing` module — add a walltime-sizing function symmetric to
  `peak_informed_memory_gb`,
- in-loop partial-`trace.txt` parsing at heal-decision time,
- the `apply_patch` `observed_target_*` override seam.

Keep it a **two-tier ladder**: (a) the killed task's observed `realtime × multiplier`,
else (b) blind `× 2` fallback when no usable `realtime` exists (trace-less, snakemake,
`-`/0 value). The 72 h ceiling clamp (`CEILING_TIME_H`), the never-shrink rule, and the
`gave_up_at_ceiling` give-up all stay exactly as in the memory slice. Nextflow-only; no
verdict / exit-code / `FailureClass` change. Surface the observed `realtime`, the sizing,
and the evidence tier in `RepairStep.detail`, exactly as the peak-RSS slice does.

## The one honest caveat (right-censoring — weaker signal than peak RSS)

Walltime observations are **right-censored** in a way peak RSS is not. A task killed at
the limit reports `realtime ≈ current limit`, so its own observation only proves
"needed ≥ current" — a genuinely weaker signal than a true observed memory peak (which
is a real maximum below the limit). Design implications to resolve in the PRD:

1. The multiplier must be chosen deliberately so a task that just grazed the limit still
   gets a sensible bump (not a blind double, but not a no-op either).
2. Prefer a **non-killed sibling task's** `realtime` where the trace carries one — an
   uncensored observation is stronger than the killed task's censored one. (Mirror-caveat
   to the peak-RSS "same-process sibling rescue" that was deferred because the parser sets
   `process == name` for every row — confirm whether that blocks sibling use here too.)
3. Scope the win honestly: this is a smaller, more-censored win than the memory slice.

## Confirmed code facts (from the peak-RSS predecessor card — re-verify in Phase 2)

- `self_heal.py:43-47` — `_DEFAULT_MEMORY_GB = 8`, `CEILING_MEMORY_GB = 128`,
  `CEILING_TIME_H = 72`.
- `self_heal.py:404-412` — `_resource_ceiling_block` gates `gave_up_at_ceiling` for
  `oom` (memory) and `time_limit` (time).
- `self_heal.py:446-464` — `apply_patch` resource branch: blind `current * mult`,
  `min(bumped, ceiling)`, `max(capped, current)` never-shrink. v0.19.0 added an
  `observed_target_gb` override here — the walltime analogue overrides the time branch.
- `models.py:118-131` — `TaskResource{process, name, realtime_sec, peak_rss_mb, pct_cpu}`.
  Walltime sizing reads `realtime_sec` (the memory slice read `peak_rss_mb`).
- `events.py` — `parse_resource_usage_text` / `parse_resource_usage_file` (the same trace
  reader the memory slice reused in-loop).
- `resource_sizing.py` — new module from v0.19.0 with `peak_informed_memory_gb`; add the
  symmetric `realtime_informed_time_h` (or similarly named) here.

## Definition of done (from the brief)

- Build **test-first** with injected trace/executor fixtures (no real pipeline run in CI).
- Sized `time_limit` retry when observed `realtime` is present; blind-`×2` fallback when absent.
- 72 h ceiling clamp + `gave_up_at_ceiling` give-up preserved; never-shrink preserved.
- Memory path (peak-RSS scaling) untouched.
- Capture observed-`realtime`-vs-requested + sized-retry outcome / evidence tier in
  `RepairStep.detail` for the corpus.

## Grounding references (moat — files, not memory)

- `CHANGELOG.md` v0.19.0 — peak-RSS OOM memory scaling (the slice this mirrors; names the
  walltime follow-on as deferred).
- `docs/technical/CAPABILITY_ROADMAP.md` C2 (`:227`) — "**walltime** sizing to observed
  `realtime`" named as deferred.
- `docs/planning/peak-rss-resource-scaling/prd.md:158` — "Walltime / `time_limit` sizing
  to observed `realtime_sec`. Symmetric follow-on slice."
- `docs/planning/peak-rss-resource-scaling/sizing/` — the tech plan for the memory slice
  to mirror structurally.

## Strategic guardrail check

Stays in **Layer 2** (run/self-heal/verify/reproduce). No Layer-1 workflow authoring,
no wet-lab/clinical credentials, no raw-read egress (operates on the run's own trace on
the user's compute). ✅
