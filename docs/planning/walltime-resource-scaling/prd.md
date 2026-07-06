# PRD — Walltime-informed self-heal resource scaling

**Capability:** C2 (self-heal breadth + auto resource-scaling).
**Slice:** the symmetric walltime follow-on to v0.19.0's peak-RSS OOM memory scaling.
**Branch:** `feat/self-heal-walltime-scaling/aliz`. **Slug:** `walltime-resource-scaling`.
**Design decision (locked with the user):** ship the **honest, never-worse-than-blind
instrument**, not a naive factor-mirror. See §Problem for why.

---

## Problem Statement

When a Nextflow task is killed for exceeding its wall-clock time (`time_limit`), the
self-heal retry today multiplies the time allowance **blindly** by 2 and retries
(`repair.py:26-35` → `apply_patch` time branch, `self_heal.py:490-495`). v0.19.0 replaced
the analogous *memory* blind-double with sizing to the failed task's **observed peak RSS**
from the run's own `trace.txt`. The walltime path was explicitly deferred as the symmetric
follow-on (`CHANGELOG.md` v0.19.0; `CAPABILITY_ROADMAP.md` C2 `:227`;
`peak-rss-resource-scaling/prd.md:158`).

**But walltime is not memory, and the Phase-2 dig proved the signal is materially weaker.**
This PRD is honest about that up front because it shapes the whole design:

- **Memory works** because an OOM'd task's `peak_rss` is its *actual high-water mark* — a
  real (≈) measure of demand. `peak × 1.5` = demand + headroom.
- **A walltime-killed task never finished**, so its `realtime` is only a **lower bound** on
  the time it needed, and it is **hard-censored at ≈ the current limit** (the scheduler's
  timer fires right at the cap; ~no overshoot). `time_limit` is detected from log text only
  (`detect.py:55-64`) — there is no exit-code high-water signal analogous to OOM's `137`.
- **Therefore a naive mirror** (`realtime × 1.5`) sizes retries to `≈ current × 1.5`, which
  is **less aggressive than today's blind `× 2`** — it would *slow* convergence and burn
  more of the bounded retry budget. That is a regression, and it violates the "never regress
  a working heal" invariant the memory slice held.

**Who has the problem.** The lone computational biologist / core facility running real
pipelines unattended on SLURM/cloud, where long-pole tasks intermittently exceed their
walltime label and the agent must recover without a human (ROADMAP Phase-1 unattended-
completion metric).

**Why build it anyway (scoped honestly).** There *is* a real signal in the **tail**: when
the trace shows a `realtime` **above** the current limit — a higher-label sibling process
that also timed out, a mis-classified `time_limit` (something else killed a long-running
task), or grace/staging overrun recorded past the cap. In those cases `observed × factor >
blind`, and we do better. Everywhere else we tie blind. Crucially, the slice's real payload
is a **field instrument**: every walltime heal records observed-`realtime`-vs-limit into
`RepairStep.detail`, so we learn — from real runs — how often a walltime kill even carries
a usable signal. That is moat-#2 eval data and it de-risks whether to invest further here.
This is the exact posture v0.19.0's CHANGELOG took for `peak_rss` ("the instrument that
will show, in the field, how often real OOM'd tasks even carry a usable `peak_rss`").

---

## Goals & Success Metrics

1. **Never worse than blind.** For any walltime heal where the observed signal is censored
   at ≈ the current limit (the common case), the retry allowance equals today's blind `× 2`.
   *Measure:* a regression test proving `time = 4h → 8h` when observed `realtime ≈ 4h`.
2. **Better in the tail.** When the trace carries a `realtime` above the current limit, the
   retry is sized to `ceil(max_realtime/3600 × factor)`, exceeding blind. *Measure:* a test
   with an observed `realtime` of e.g. 10h under a 4h limit → retry `≥ 15h` (factor 1.5),
   not 8h.
3. **Instrumented.** Every walltime heal writes observed max `realtime`, the sizing, the
   evidence tier, and whether it beat blind into `RepairStep.detail`. *Measure:* integration
   test asserts the detail string content on both tail and common-case paths.
4. **Zero blast radius on the shipped memory slice, verdict, and reproduce.** Memory sizing,
   exit codes, `FailureClass`, and the run record are byte-for-byte unchanged. *Measure:*
   the existing memory-sizing and reproduce tests pass untouched.

Non-metric guardrail: no over-claiming. The feature never asserts "the task needed X hours";
`realtime` at kill is a lower bound and the telemetry says so.

**Revisit trigger (the whole point of the instrument).** This slice is justified as a cheap
probe: after **≥ 20 observed walltime heals** in the field (or the first design-partner run
that exercises walltime repeatedly), pull the observed-`realtime`-vs-limit stat from
`RepairStep.detail`. **If the tail case (observed > current limit) fires in < ~20% of walltime
heals**, do **not** invest further in walltime sizing (no sibling-rescue tier, no calibration)
— redirect C2 effort to a new failure class instead. This decision trigger is the deliverable
as much as the code is.

---

## User Personas & Scenarios

- **A — lone computational biologist**, unattended overnight run on SLURM. A `salmon`
  task's 4h label is short for a large cohort; it's killed at 4h. Today: blind → 8h, retry.
  With this slice: the trace's max `realtime ≈ 4h` (censored) → floored to 8h — identical
  behavior, plus a detail line recording that the signal was censored. No regression.
- **C — core facility**, mixed-label workflow. A high-label `star_align` task times out but
  the trace also shows a concurrent long task at 9h under its own shorter label
  (mis-labeled). Max observed `realtime = 9h > 4h current` → retry sized to 14h (9 × 1.5,
  ceil), beating blind's 8h, recovering in one round instead of two.

---

## Requirements

### Must-have

- **M1 — Pure walltime sizer.** New `resource_sizing.realtime_informed_time_h(events,
  usage, *, factor=WALLTIME_SAFETY_FACTOR) -> TimeSizing(target_h|None, tier,
  observed_realtime_sec|None)`. Computes `math.ceil(max_realtime_sec / 3600 × factor)` over
  `usage` rows with `realtime_sec > 0`. Returns `(None, "unavailable", None)` when no row
  has a usable `realtime`. Keys on **max realtime across all rows** (not `exit==137` —
  `time_limit` has no exit-code join key); floor-at-blind (M2) makes max-over-rows safe.
- **M2 — `apply_patch` observed override with floor-at-blind.** Add keyword
  `observed_target_h: int | None = None`. Time branch becomes
  `bumped = max(observed_target_h, int(current*mult)) if observed_target_h is not None else
  int(current*mult)`. **This `max(...)` floor is the one intentional asymmetry vs the memory
  branch** (memory trusts observed even below blind; walltime must never dip below blind
  because its observation is a censored lower bound). Ceiling clamp (`min(bumped, ceiling)`)
  and never-shrink (`max(capped, current)`) unchanged; unit stays `f"{final}.h"`.
- **M3 — Heal-site wiring.** A `_time_limit_sizing(diagnosis, run_dir, events)` sibling to
  `_oom_memory_sizing` (`self_heal.py:417-439`), gated on `failure_class == "time_limit"`,
  parses the partial `trace.txt` in-loop (reuse `parse_resource_usage_file`) and returns
  `(target_h, detail)`. At the safe-path call site (`self_heal.py:1008-1018`) compute both
  memory and time sizings and pass both overrides into `apply_patch`. A single attempt is
  one failure class, so only one override is ever non-None.
- **M4 — Telemetry.** `RepairStep.detail` records: `"scaled time to ~{target_h}h from
  observed realtime {sec:.0f}s (x{factor}, {tier}); {beat blind | tied blind (censored)}"`
  on the sized path, and `"no usable observed realtime; blind x2 fallback (unavailable)"`
  when absent. Where cheaply available, also note whether the max-`realtime` row coincides
  with a failed event (R3) so field data can judge whether the tail signal is the bottleneck.
  No model change (`detail` is already `str | None`, `models.py:251-258`).
- **M5 — Regression guards.** (a) A censored-signal test proving parity with blind `× 2`.
  (b) A memory-branch-untouched test (invert the existing
  `test_apply_patch_observed_target_leaves_time_branch_unaffected`,
  `test_self_heal.py:719-738`). (c) The existing memory-sizing + `gave_up_at_ceiling` time
  tests pass unchanged.

### Should-have

- **S1 — Ceiling give-up unchanged & retested.** `_resource_ceiling_block` already gates
  `time_limit` at `CEILING_TIME_H` (`self_heal.py:405-414`); reuse
  `test_gives_up_at_time_ceiling` (`test_self_heal.py:1206-1225`) as the walltime ceiling
  regression. No code change here — assert it still holds with sizing in the loop.

### Nice-to-have (explicitly deferred — see Out of Scope)

- Sibling-task uncensored-`realtime` rescue tier; walltime corpus-schema capture; folding
  the observed-vs-limit stat into the C6 eval flywheel.

---

## Technical Considerations

- **Where it sits:** entirely in the self-heal loop (run → **self-heal** → verify →
  reproduce). No planner, verdict, or dashboard change.
- **Reuse, exactly as the memory slice:** `resource_sizing.py` pure module +
  `TimeSizing` NamedTuple sibling to `PeakSizing`; the in-loop `parse_resource_usage_file`;
  the `apply_patch` override seam. `realtime_sec` is already parsed (`events.py:128-135`)
  and on `TaskResource` (`models.py:118-130`) — **no parser or model change**.
- **Unit correctness:** `realtime_sec` is **seconds** in the trace; config time is **hours**
  (`{final}.h`, `_DEFAULT_TIME_HOURS = 4`, `CEILING_TIME_H = 72`). The sizer converts
  `sec / 3600` before the factor and `math.ceil` to whole hours.
- **Reproducibility:** no scratch path or new manifest field; `rerun`/`resume` re-derive the
  heal from the same trace, unchanged.
- **Determinism / privacy:** reads the run's own `trace.txt` on the user's compute; no
  network, no raw-read egress; Nextflow-only (snakemake's `stats.json` isn't TSV-parsed →
  falls through to blind, unchanged).

---

## Risks & Open Questions

- **R1 (accepted, by design):** the observed signal is usually censored at the limit, so the
  feature is a no-op-vs-blind in the common case. *Mitigation:* that's the chosen scope; the
  value is the tail + the telemetry. Documented honestly in the CHANGELOG.
- **R2 — `factor` default.** Set to **1.5** to mirror memory's `PEAK_RSS_SAFETY_FACTOR`,
  as an *uncalibrated engineering default* (repo convention). Open: should the walltime
  factor differ? Recommend 1.5 for symmetry; revisit when field telemetry lands.
- **R3 — max-over-all-rows vs the timed-out task.** Chosen: max over all rows, because
  log-only `time_limit` detection cannot reliably pin a trace row, and floor-at-blind makes
  a too-small max harmless and a large max (the tail win) is exactly what we want to catch.
  **Honest framing:** the tail win is *opportunistic* — the max-`realtime` row is not
  guaranteed to be the timed-out task (an unrelated long-but-successful task could set the
  max). Floor-at-blind + the 72h ceiling clamp bound the downside to "never worse than blind,
  never above the cap." The telemetry (M4) additionally records whether the max-`realtime`
  row coincides with a failed/`is_failure` event, so the field data can later tell us how
  often the tail signal is actually the bottleneck vs a bystander.
- **R5 — double override (defensive).** `apply_patch` could in principle receive both
  `observed_target_gb` and `observed_target_h`. It cannot in practice (one `failure_class`
  per attempt → at most one sizer returns non-None), but the invariant is asserted and tested
  rather than left to a comment.
- **R4 — does a walltime-killed row even carry `realtime`?** Empirically uncertain (same
  class of risk the memory slice named for `peak_rss`). The two-tier ladder (observed → blind
  fallback) means "no usable realtime" degrades to today's behavior; the telemetry measures
  how often it happens. No correctness risk.

---

## Out of Scope

- **Memory / peak-RSS sizing** — shipped in v0.19.0, untouched here.
- **Sibling-task rescue** — borrowing an uncensored sibling's `realtime` is unreachable
  while the parser sets `process == name` for every row (`events.py:127,131`); needs a
  coarse `process` column (a `progress.py` blast radius). Deferred, identical to the memory
  slice's deferred sibling rung.
- **Snakemake** walltime sizing; any **verdict / exit-code / `FailureClass`** change; a new
  **corpus-schema** field for observed realtime (telemetry rides in `RepairStep.detail`).
- **Calibrating** the factor or the ceiling against real data (uncalibrated defaults stand).

---

## Acceptance (test-first, no real pipeline in CI)

1. **Sizer unit** (`tests/test_resource_sizing.py`): tail (max realtime 10h → 15h @1.5);
   censored/common (realtime 4h → 6h *raw*, floored to blind only in `apply_patch`);
   unavailable (all rows `realtime 0`/dash → `None`); empty inputs → `None`;
   `math.ceil` boundary; default-factor constant.
2. **`apply_patch` seam unit** (`tests/test_self_heal.py`): override beats blind in the tail;
   **override floored to blind when below** (the walltime-specific `max`); `None` preserves
   blind; ceiling clamp; never-shrink; **memory branch unaffected by `observed_target_h`**;
   **both overrides present** → memory and time each honored independently (R5 invariant).
3. **Integration** through the fake executor (mirror `test_self_heal.py:2450-2548`): a
   tail-signal trace → sized-up retry + `detail` names observed realtime and "beat blind";
   a censored trace → blind-parity retry + `detail` names "tied blind (censored)"; a
   trace-less/`realtime`-absent run → blind fallback + `detail` "unavailable".
4. **Regression:** `test_gives_up_at_time_ceiling` and all memory-sizing tests pass
   unchanged.
