# Card: feat / peak-rss-resource-scaling

- **Type:** feat
- **Id/slug:** peak-rss-resource-scaling
- **Owner:** aliz
- **Branch:** feat/peak-rss-resource-scaling/aliz
- **Source:** inline brief (no GitHub issue — slug work, handed off from `contig-next`)

## Brief

Make the OOM/walltime self-heal **evidence-based** instead of blindly multiplicative.

Today an OOM heal blindly multiplies memory (`src/contig/self_heal.py:450-455`,
`bumped = int(current * int(mult["memory"]))`) and retries, clamped to the 128 GB
ceiling (`CEILING_MEMORY_GB`). This slice makes the retry sized to the failed task's
**actual observed peak memory**: at heal-decision time, parse the run's partial
`trace.txt` (reuse `events.parse_resource_usage_text`), find the OOM'd process's
`peak_rss_mb` (`TaskResource.peak_rss_mb`, `models.py:129`), and size the memory
retry to `observed_peak × safety_factor` instead of the blind multiplier — still
clamped to the existing ceiling and preserving the `gave_up_at_ceiling` give-up.

## Why (moat grounding — files, not memory)

- Explicitly the **next-named C2 slice**: `docs/technical/CAPABILITY_ROADMAP.md:210-212`
  lists "peak-RSS-informed scaling (needs a refactor — `resource_usage` is only populated
  at finalize, after the patch decision)" as pending.
- Deepens the headline moat — **recover more failures without a human**
  (unattended-completion, `docs/ROADMAP.md:101`, `CAPABILITY_ROADMAP.md:223`). Blind
  doubling needs 3 rounds to reach 5× (2→4→8×) and can exhaust the bounded retry budget
  or overshoot; sizing to observed peak lands in one round.
- Guaranteed **live trigger** (OOM happens on real runs; the trace is real), unlike the
  BWA/bwa-mem2 items deferred for *no* live trigger (`CHANGELOG.md:279`).
- Captures richer **eval data**: observed-peak-vs-requested delta + whether the sized
  retry succeeded (moat #2, `CAPABILITY_ROADMAP.md:243`).

## The one honest caveat (blocker named in the roadmap)

`CAPABILITY_ROADMAP.md:211`: `resource_usage` is populated at **finalize**, after the
patch decision — and is only consumed at finalize/estimate today (`cli.py:1072`,
`estimate.py:91-96`), never in the heal path (`self_heal.py:450-455`). So the slice must:

1. Parse the **partial/failed-run trace at heal-decision time** (the same `trace.txt`
   `events.parse_resource_usage_text` already reads), and map the OOM'd process to its
   `peak_rss_mb`.
2. **Fall back to the existing blind multiplier when observed peak is unavailable** — a
   killed task often has no flushed peak-RSS trace row. Never regress an already-working
   heal.
3. Keep the ceiling clamp and the `gave_up_at_ceiling` give-up intact.

## Confirmed code facts (grounding pass)

- `self_heal.py:43-47` — `_DEFAULT_MEMORY_GB = 8`, `CEILING_MEMORY_GB = 128`,
  `CEILING_TIME_H = 72`.
- `self_heal.py:404-412` — `_resource_ceiling_block` gates `gave_up_at_ceiling` for
  `oom` (memory) and `time_limit` (time).
- `self_heal.py:446-464` — `apply_patch` resource branch: blind `current * mult`,
  `min(bumped, ceiling)`, `max(capped, current)` never-shrink.
- `models.py:118-131` — `TaskResource{process, name, realtime_sec, peak_rss_mb, pct_cpu}`.
- `events.py:106` `parse_resource_usage_text`, `:140` `parse_resource_usage_file`.

## Definition of done (from the brief)

- Build **test-first** with injected trace/executor fixtures (no real pipeline run in CI).
- Sized retry when observed peak is present; blind-multiplier fallback when absent.
- Ceiling clamp + `gave_up_at_ceiling` give-up preserved.
- Capture observed-peak-vs-requested + sized-retry outcome as eval data for the corpus.

## Strategic guardrail check

Stays in **Layer 2** (run/self-heal/verify/reproduce). No Layer-1 workflow authoring,
no wet-lab/clinical credentials, no raw-read egress (operates on the run's own trace on
the user's compute). ✅
