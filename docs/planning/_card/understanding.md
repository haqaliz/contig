# resource-aware-retry — Phase 2 understanding

Graphify-first code map, confirmed by reading the worktree. File:line against
`feat/resource-aware-retry/aliz`.

## What the work is really asking

Make the self-heal loop's `oom` and `time_limit` repairs **bounded and
convergent**: scale the failed process's memory/time up to a **ceiling**, never
past it, with a retry budget that provably terminates, and record the scaling
honestly. This is the first slice of C2 (`CAPABILITY_ROADMAP.md:94-124`).

## The single most important finding (reframes the slice)

**Progressive scaling already happens implicitly; the missing piece is the
ceiling + convergence, not the progression.**

- `apply_patch` (`self_heal.py:259-300`) multiplies the **current** target's
  `resource_limits` each attempt, and `current_target` is carried forward across
  the loop (`self_heal.py:508` -> next `run_pipeline` at `:342`). So OOM at attempt 1
  takes memory 16->32 GB, OOM at attempt 2 takes 32->64 GB, etc. -- geometric already.
- What is genuinely absent: (a) any **ceiling** so the value can't grow without
  limit; (b) a **give-up-at-ceiling** path so the loop doesn't burn its remaining
  budget re-running the same too-small (or absurdly-large) size; (c) a **structured
  record** that the scaling hit/honored the ceiling; (d) a **test** proving the
  loop terminates.

So slice 1 ~= "add a bounded resource ceiling to `apply_patch` resource scaling,
clamp to it, stop scaling when already at it, and prove termination."

## Affected areas (precise)

| Area | File:line | Role today |
|---|---|---|
| OOM/time_limit detection | `detect.py:42-64` | Returns `Diagnosis(failure_class="oom"\|"time_limit")`. **Do not touch.** |
| Patch proposal | `repair.py:16-35` | Hardcodes `{"multiply": {"memory": 2}}` / `{"multiply": {"time": 2}}`, `risk="safe"`. Takes only `diagnosis` (no attempt/ceiling state). |
| Patch application | `self_heal.py:259-300` (`apply_patch`) | Interprets `multiply`, `_lead_number` x factor, writes `"{n}.GB"`/`"{n}.h"` into `ExecutionTarget.resource_limits`. **No ceiling.** Primary insertion point. |
| Loop + budget | `self_heal.py:303-514` | `max_attempts=3` bounds it; applies patch at `:508`; records each step `:509-513`; stashes failed attempt to pending corpus `:364-377`. |
| Config emission | `nfconfig.py:59-68` | `process.resourceLimits = [ memory: 16.GB, cpus: 2, time: 24.h ]`; keys exactly `memory`/`cpus`/`time`; units GB/unitless/h. |
| Models | `models.py` | `Patch` (`:211`, untyped `operation` dict), `Diagnosis` (`:202`), `RepairStep` (`:225`, `outcome: str`), `FailureClass` (`:182`), `TaskResource` (`:118`), `RunRecord.resource_usage` (`:254`). |
| Executor seam | `runner.py:72,230,252` | `Executor = Callable[[list[str], Path], int]`; injectable into `run_pipeline(executor=...)`. Tests inject a fake that OOMs then succeeds. |

## Contradiction / blocker surfaced (must shape scope)

**Peak-RSS-informed scaling is NOT feasible in this slice without a refactor.**
`resource_usage` (peak_rss_mb per task) is only populated in `_finalize()`
(`self_heal.py:541`), which runs *after* the patch decision. At the
`PipelineExecutionError` catch point (`:360-378`) `exc.record` has events but **no**
`resource_usage`. So "read peak RSS and scale to fit" requires either populating
`exc.record.resource_usage` before raising in `run_pipeline`, or parsing the trace
at catch time. Recommend: **slice 1 is purely multiplicative + ceiling** (stays
deterministic, no readback); peak-RSS-informed scaling is a deferred follow-on with
a named refactor. Flag this in the PRD, don't paper over it.

## Design tensions for the interview

1. **Where the ceiling lives.** `propose_patches(diagnosis)` has no attempt/ceiling
   context. Cleanest: enforce the ceiling in `apply_patch` (it already owns the
   numeric mutation), passing a ceiling policy in. Patch stays declarative.
2. **Ceiling policy.** Absolute caps (memory <= N GB, time <= T h) vs a multiple of
   the original request (<= 8x). Absolute is simpler to reason about and to surface
   ("needs a bigger box than 128 GB"); a multiple needs the original remembered.
3. **At-ceiling behaviour.** When the next scale would exceed the cap: clamp to the
   cap and try once more, then on the *next* OOM at the cap, **give up with a clear
   message** (a new outcome / `expected_signal`), never a false PASS. Don't keep
   retrying the same capped size.
4. **Budget/termination.** `max_attempts=3` already bounds it; the new test must
   prove that even with scaling, the loop terminates (no infinite re-scale), and
   that a clamp-then-give-up path is taken at the ceiling.
5. **Structured record.** Surface the scaling outcome (scaled / clamped-to-ceiling /
   gave-up-at-ceiling) on the `RepairStep`/patch so the dashboard and corpus label
   it. Decide whether this needs a new `RepairStep` field or fits `outcome: str`.

## Guardrails honoured

Layer 2 only (run + self-heal), no raw-read egress, bounded + logged self-heal,
test-first with the injected `Executor` (no real Nextflow/tool execution). No
Layer-1 drift.
