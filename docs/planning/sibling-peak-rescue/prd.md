# PRD: sibling-peak-rescue

Status: **SHIPPED (Unreleased, 2026-09-13).** Landed on
`feat/sibling-peak-rescue/aliz` as `bbaf8f6` (parser prerequisite), `857f1eb`
(sibling sizer rung, flipping the no-rescue pin), `da926b7` (heal-site wiring +
telemetry), and the docs commit (changelog/roadmap corrections). This document
remains the record of intent; the shipped details are in the changelog entry.

Status: draft for review. Owner: aliz. Branch: `feat/sibling-peak-rescue/aliz`.

Source: inline brief (`docs/planning/_card/issue.md`) selected by `contig-next`;
dig note: `docs/planning/sibling-peak-rescue/understanding.md`.

---

## Problem statement

The shipped peak-RSS memory self-heal (C2, `peak-rss-resource-scaling`) sizes an
OOM retry from the failed task's **own** observed `peak_rss` when one exists
(`PeakSizing` tier `"oom_task"`), and otherwise falls back to a blind `current × 2`
bump (tier `"unavailable"`). The censored case is real: a signal-killed task can
leave a `-`/0 `peak_rss` in `trace.txt`, and a trace-less run has no rows at all.
In that case the engine has evidence it is not using — the **same-process
sibling** rows of the failed task, whose peaks are observed under the same global
`process.resourceLimits` (`nfconfig.py:68`) the retry will re-apply. Both parent
slices deferred exactly this rung, twice, for one reason: the trace parser aliases
the coarse Nextflow `process` column to the per-task `name`
(`events.py:91` TaskEvent, `events.py:130` TaskResource), so same-process grouping
is impossible (`peak-rss-resource-scaling/prd.md:155-157`,
`walltime-resource-scaling/prd.md:194-197`).

This slice is the deferred rung: **fix the parser, add the sibling tier, land the
telemetry.** The honest value is *precision* — sizing to observed usage instead of
a blind multiplier when the failed task's own high-water mark is censored — not
"recover more failures": a surviving sibling's peak is bounded by the very limit
that killed the failed task, so the sibling-informed target can never beat blind
`× 2`; it can only be a tighter (or equal, or no) bump. Stated up front, like the
walltime slice's censored-lower-bound honesty (`walltime-resource-scaling/prd.md:21-22`).

## Goals & Success Metrics

Test-first; the acceptance is a set of failing tests written before the code, per
the repo's standing discipline. No real Nextflow run in CI.

| # | Goal | Success criterion (test) |
|---|------|--------------------------|
| G1 | Parser exposes the coarse `process` column | A trace with both `process` and `name` columns yields `TaskEvent.process` = the coarse value (not the task name), and the same for `TaskResource.process`; a trace *without* the column keeps today's `name` fallback, so all existing fixtures and tests pass unchanged |
| G2 | Sibling rung fires only when it beats `current` | OOM'd task with censored peak + same-process sibling with positive peak, `ceil(peak × 1.5) > current` → `PeakSizing(target, tier="sibling_peak", observed_peak_mb, source_name)`; sibling candidate `≤ current` → `PeakSizing(None, tier="sibling_dominated", …)` and the caller falls back to blind `× 2` — **never a no-op retry with an unchanged limit** |
| G3 | Existing ladder untouched when it applies | Own-peak present → tier `"oom_task"` unchanged; multi-OOM max unchanged; no sibling and no own peak → tier `"unavailable"` unchanged |
| G4 | `apply_patch` contract unchanged | `observed_target_gb`/`observed_target_h` seams, ceiling clamp, never-shrink, and `gave_up_at_ceiling` tests all pass unchanged |
| G5 | Telemetry names the evidence | `RepairStep.detail` records the tier, the borrowed sibling's value and task name (`source_name`), and the fallback reason on `sibling_dominated`; heal-guard/eval-guard baselines unmoved (the `oom` heal scenario's trace carries no peak column, so it stays on the blind path) |

**Honest framing, in the parent slices' words:** we do **not** claim a % lift or
"recovered more runs". Organic frequency of the censored case is unmeasured —
no real Contig-launched run has ever produced it, and the field corpus has only
ever diagnosed `oom`/`tool_crash`/`missing_index`/`unknown`. The **precision
claim is likewise a hypothesis, not a finding**: a surviving sibling's peak is
bounded by the failed limit, so the sibling-informed target is a tighter bump
than blind only when the sibling ran near the limit — and whether that happens
in the field is exactly what the telemetry measures. The telemetry is the
deliverable's second half: it tells us whether the sibling rung ever fires
(`sibling_peak` vs `sibling_dominated` vs `unavailable`, counted from
`RepairStep.detail` across runs) **and whether a sibling-sized retry recovered**
(its `RepairStep` outcome, read from the same `repair_history`). **Revisit
trigger** (mirrors the walltime slice's, `walltime-resource-scaling/prd.md:72-78`):
if the sibling tiers fire in **0 of the next 20 real OOM heals**, the rung is
restated as taxonomy-only and no further effort goes into it — counted by
grouping `RepairStep.detail` tier tokens, no new instrumentation.

## User Personas & Scenarios

Not a user-facing feature; the persona is **the unattended run** (ROADMAP Phase 1:
"reliable enough to use unattended on real, messy data", ≥70% unattended
completion). Scenario: a pipeline task is OOM-killed under a process-wide limit;
the killed row's `peak_rss` is `-`/0, but a sibling task in the same coarse
process completed at a known peak. Today the retry doubles the limit blindly;
with this slice it sizes to the observed sibling peak when that strictly exceeds
the current limit (tighter convergence toward the ceiling, less over-allocation),
and records which tier fired so the decision can be judged later.

## Requirements

**Must-have**
1. `events.py`: both parsers (`parse_trace_text`, `parse_resource_usage_text`)
   read the coarse `process` column by header name, falling back to `name or ""`
   when absent. Header-driven resolution unchanged (no positional assumptions).
2. `resource_sizing.py`: `peak_informed_memory_gb` gains the sibling rung —
   when no OOM'd task has a usable own peak, collect the max positive
   `peak_rss` over rows whose coarse `process` matches an OOM'd task's process.
   Emit `PeakSizing(target_gb, tier="sibling_peak", observed_peak_mb,
   source_name)` when the candidate strictly exceeds `current_gb` (new optional
   `current_gb` parameter; pure, no I/O); emit
   `PeakSizing(None, tier="sibling_dominated", …)` otherwise.
3. `self_heal.py::_oom_memory_sizing`: read the current memory limit **tolerantly**
   (a `_lead_number`-style parse of the `"64.GB"` string; an absent/unparseable
   limit degrades to the blind path, never a crash), pass it in, and build the
   two new detail strings — `sibling_peak` ("scaled memory to ~X GB from
   same-process sibling peak Y MB (x1.5, sibling_peak, borrowed from <name>; vs
   blind x2)", naming whether the applied limit beat or tied blind) and
   `sibling_dominated` ("sibling peak Y MB not strictly larger than current;
   blind x2 fallback (sibling_dominated)"). The `unavailable` fallback text is
   unchanged for the no-sibling case.
4. Tests, RED first: flip `test_same_process_sibling_is_not_rescued`
   (`tests/test_resource_sizing.py:65-79`) — a **deliberate contract change** to a
   shipped test, disclosed like the `qc_anomaly` `recovered` flip — plus new
   dominated-tier, no-sibling, and coarse-column parser tests, and a
   fake-executor integration test mirroring `test_self_heal_sizes_oom_retry_from_observed_peak`
   (`tests/test_self_heal.py:3110-3136`).

**Should-have**
5. `PeakSizing`/`TimeSizing` NamedTuples gain `source_name: str | None = None`
   (defaulted; keyword-constructed everywhere, so no call-site break).
6. The `events.py` module docstring (`:4-7`) is corrected to the real default
   column set (it omits `process`, `peak_rss`, `%cpu`).

**Nice-to-have**
7. A `contig show`/text-report surface change is **not** needed — the tier rides
   in `RepairStep.detail` as shipped; no surface edits.

## Technical Considerations

- **Parser fix is the prerequisite and the risk.** The `(process, name)` join key
  in `resource_sizing.py:57-61` is only correct today because *both* parsers
  alias identically — the two one-line edits must land together or the own-peak
  tier silently breaks. Both parsers are header-driven
  (`events.py:78,118`), and real traces already carry the column (plain
  `-with-trace`, no `trace.fields` override, `runner.py:1321-1322`).
- **Blast radius of the `process` field** (now that it stops aliasing):
  `progress.py:71,152` (display-only; shows the coarse process — the roadmap's
  "blast radius" is real but cosmetic), `detect.py:621` (LLM-prompt text only;
  the rules detector never reads `process`), `stall.py` (does not parse),
  `heal.py` (writes traces, never parses). Dashboard: no change — its TS parser
  already reads the coarse column with a `|| name` fallback
  (`dashboard/lib/runs.ts:222,233-237`).
- **`current_gb` in the sizer** keeps the "strictly larger" decision pure and
  testable; `_oom_memory_sizing` already has the current limit in scope
  (`self_heal.py:1616-1624` region).
- **Asymmetry vs tier a, stated:** tier `"oom_task"` (shipped) may also produce a
  target below `current` and then ride never-shrink to a no-op retry — that is
  shipped behavior and deliberately **not** changed here. The strict-larger guard
  applies to the sibling rung only, because a sibling's peak is weaker evidence
  (it never measures the failed task) and a no-op retry there would be a
  regression vs blind.
- **Trace accumulation across attempts** is not modeled; the sizer reads all rows
  in the file, exactly as tier a does today. Consistency, not improvement.
- Dependencies: none new (stdlib). No model/signature/`FailureClass` change.
  No real Nextflow in CI.

## Risks & Open Questions

| # | Risk | Likelihood | Impact | Mitigation / Test |
|---|------|-----------|--------|-------------------|
| R1 | Sibling tier never fires in the field (censored case rare) | Med | Low | The revisit trigger (0/20 heals → taxonomy-only) is the deliverable's guard; telemetry counts the tiers |
| R2 | A sibling-sized retry under-sizes and the blind bump would have succeeded | Med | Low | Bounded by the retry budget and ceiling; the loop re-sizes each attempt from the freshest trace; tier recorded so the call can be judged |
| R3 | Parser change breaks the own-peak join or a consumer | Low | Med | Both parser edits land in one commit; join-key and progress tests pin the consumers; `test_columns_resolved_by_header_name_not_position` guards the header-driven contract |
| R4 | `sibling_dominated` fallback misreads as a recoverable tier by future tooling | Low | Low | The tier literal is distinct from `unavailable` on purpose; the detail text names the fallback reason |

Open questions: none blocking. (Whether to *narrow* the walltime sizer to
same-process siblings is **declined by design** — see Out of Scope; the global
max is shipped behavior and already the superset.)

## Out of Scope

- **Walltime branch changes.** `realtime_informed_time_h` already takes a global
  max realtime (`resource_sizing.py:114`) — the roadmap's "same
  `process == name` blocker as memory" for the sibling-`realtime` rescue
  (`CAPABILITY_ROADMAP.md:299-301`) is **inaccurate as written**; this slice
  corrects the prose and touches no time-branch code.
- **FailureCase corpus fold-in** (the brief's optional half). The observed peak
  already rides in the signed `RepairStep.detail`; the corpus has no consumer for
  a numeric peak, and threading it requires reordering the pending append
  (`self_heal.py:1322` vs `:1616`). Filed as a named follow-on with the
  ordering constraint recorded in the understanding note.
- Snakemake; any verdict/exit-code/`FailureClass` change; tier-`"oom_task"`
  behavior; heal-guard scenario additions; calibration of the 1.5× factor or the
  ceilings; dashboard changes.