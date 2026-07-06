# Understanding — self-heal-walltime-scaling (Phase 2 deep dig)

Synthesized from a read-only code-mapping agent over this worktree (master, incl.
v0.19.0 peak-RSS memory scaling). Refs are `src/contig/*`; line numbers exact at dig time.

## What the work asks (as briefed)

Mirror v0.19.0's peak-RSS OOM memory scaling for **walltime**: when a task is killed for
exceeding its time limit (`time_limit` repair), size the retry to the failed task's
**observed `realtime`** from the run's partial `trace.txt`, instead of the blind
`time × 2`. Same seams: a pure sizing fn in `resource_sizing.py`, in-loop trace parse,
an `apply_patch` `observed_target_h` override, two-tier ladder (observed → blind),
telemetry in `RepairStep.detail`. Ceiling (72h) + never-shrink + `gave_up_at_ceiling`
unchanged.

## The mechanical mirror is clean — every seam already exists

- `resource_sizing.peak_informed_memory_gb` (`resource_sizing.py:42-71`) is the template:
  add `realtime_informed_time_h(events, usage, *, factor)` → `TimeSizing(target_h|None,
  tier, observed_realtime_sec|None)`, `math.ceil(sec/3600 × factor)`, `>0` guard, else
  `("unavailable", None)`.
- `apply_patch` time branch (`self_heal.py:490-495`) is still blind `× mult`; add a
  keyword `observed_target_h` exactly like `observed_target_gb` (`:480-489`). Ceiling
  clamp + never-shrink math untouched.
- `_resource_ceiling_block` (`self_heal.py:405-414`) **already** gates `time_limit` at
  `CEILING_TIME_H` — no change.
- Heal-site wiring: add a `_time_limit_sizing(diagnosis, run_dir, events)` sibling to
  `_oom_memory_sizing` (`self_heal.py:417-439`), dispatch at the safe-path call site
  (`self_heal.py:1008-1018`), pass both overrides into `apply_patch`.
- `realtime_sec` is already parsed (`events.py:128-135`), already on `TaskResource`
  (`models.py:118-130`); dash/blank → `0.0` (same `>0` guard transfers). **No parser or
  model change needed.** Unit is seconds in the trace, **hours** in the config (`{final}.h`).
- Tests: mirror `tests/test_resource_sizing.py` (pure helper) + the `apply_patch` seam
  tests (`tests/test_self_heal.py:630-738`) + the Phase-3 integration block
  (`:2450-2548`). Note `test_self_heal_time_limit_retry_is_untouched_by_sizing`
  (`:2526-2547`) currently asserts time stays blind `4h→8h` — this slice **replaces** it.

## ⚠ The sharp finding: the walltime signal is fundamentally weaker than memory's

The dig confirmed a signal asymmetry that the `contig-next` caveat only hinted at. It is
the crux of whether this slice is worth building **as briefed**:

- **Memory (why v0.19.0 works):** an OOM'd task's `peak_rss` is the **actual high-water
  mark** it reached before the kernel killed it — a real (≈) measure of its *demand*.
  `peak × 1.5` = demand + headroom. Even under cgroup enforcement where peak ≈ request,
  it's a truthful anchor.
- **Walltime (the problem):** a walltime-killed task **did not finish**, so its `realtime`
  is only a **lower bound** on the time it needed — and it is **hard-censored at ≈ the
  current limit** (the scheduler's timer fires right at the cap; unlike memory there is
  essentially no overshoot). Detection is log-text only, no exit-code high-water mark
  (`detect.py:55-64`).
- **Consequence:** a naive factor-mirror sizes the retry to `realtime × 1.5 ≈ current × 1.5`,
  which is **LESS aggressive than today's blind `× 2`**. It would slow convergence and
  burn more of the bounded retry budget (`max_attempts`) — i.e. a **regression in the
  common case**, violating the "never regress a working heal" invariant the memory slice
  held.

**Where observed realtime *does* carry real signal (the tail):** the trace shows a
`realtime` **above** the current limit — a task with a higher process label that also
timed out, a mis-classified `time_limit` (something else killed a long-running task), or
grace/staging overrun recorded past the cap. There, `observed × factor > blind`.

### Honest design to stay never-worse-than-blind

Do **not** ship the naive mirror. Either:
- **(a)** `target = max(blind_×2, ceil(observed_realtime/3600 × factor))` — floor at blind,
  only rises in the tail; **or**
- **(b)** a walltime factor ≥ 2 so `observed ≈ current` ties blind and only the tail wins.

Both make the feature **blind-equivalent in the common censored case + a small win in the
tail + a field instrument**: record observed-realtime-vs-limit in `RepairStep.detail` to
learn how often a walltime kill even carries a usable signal — exactly the posture
v0.19.0's CHANGELOG took for `peak_rss` ("the instrument that will show, in the field...").

**Net:** this is a legitimate, safe, symmetric slice — but a **materially smaller** win
than the memory slice, not the equal-value mirror the brief implies. That is the user's
call to make before we invest in PRD/plan (below).

## Sibling-rescue is blocked here too (same as memory)

The parser sets `process == name` for every row (`events.py:127,131`), so a
"borrow a sibling task's uncensored realtime" tier is unreachable — identical to the
deferred memory sibling-rescue. Unblocking it needs a coarse `process` column (a
`progress.py` blast radius). Defer, same as v0.19.0.

## Guardrail check

Layer 2 (self-heal), local, deterministic, no raw-read egress (reads the run's own trace
on the user's compute), Nextflow-only, no verdict/exit-code/`FailureClass` change. ✅

## Decision needed before Phase 3 (PRD)

The mechanical path is trivial; the **product-value question is real**. See the fork put
to the user at the Phase-2/3 boundary.
