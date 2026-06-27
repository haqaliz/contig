# resource-aware-retry (bounded resource-aware self-heal retry)

Source: no GitHub issue. Inline brief, owner `aliz`, branch `feat/resource-aware-retry/aliz`.
Origin: first slice of capability C2 (self-heal breadth + auto resource-scaling),
`docs/technical/CAPABILITY_ROADMAP.md:94-124`. Picked by `contig-next` as the
highest-leverage next feature after v0.4.0 closed C1's turnkey follow-on.

## Brief

C2's headline item is resource-aware retry: when a process fails out-of-memory,
retry it with **scaled memory within a bounded ceiling**; when walltime is
exceeded, scale time; record the scaling as a structured patch with its rationale
and expected signal; and bound the whole thing with a retry budget that provably
converges.

Today the `oom` and `time_limit` repairs already exist but as **one-shot**
multipliers: OOM proposes `{"multiply": {"memory": 2}}` (`repair.py:16-34`) and the
self-heal loop is globally capped by `max_attempts=3` (`self_heal.py:315`). What is
missing — and what this slice adds:

- A bounded resource **ceiling** so scaling can't grow without limit.
- **Progressive** scaling that converges across attempts (not a fixed re-double
  that may overshoot or never reach the needed size within the attempt budget).
- The structured patch carrying its scaling **rationale + expected_signal**.
- A dedicated **budget test** proving the auto-scale loop terminates.
- Capture of the recovered case into the failure-and-fix corpus (moat #2 fuel).

## Why it is the moat

Unattended-completion rate is the Phase-1 headline reliability metric
(`ROADMAP.md:101`, `CAPABILITY_ROADMAP.md:100-102`). OOM is one of the named top-5
failure modes (`ROADMAP.md:56`). Incumbents only do mechanical OOM resubmit; none
records a structured, rationale-bearing scaling patch (`FEATURES.md:64`, Terra
row). Every recovered failure also seeds the detector corpus. Stays entirely Layer
2 (run + self-heal), never Layer 1.

## The caveat (hardening, not greenfield)

OOM/walltime **detection** already exists (`detect.py:42-50` for oom; time_limit
likewise), and the loop is already bounded by `max_attempts=3`. This slice must
treat detection as present and scope strictly to the **scaling / ceiling /
convergence** layer — do not re-implement detection or the outer loop.

## Scope guardrails (CLAUDE.md / FEATURES.md)

- No raw-read egress; retries run on the user's compute.
- Self-heal stays bounded and logged; the budget must provably terminate.
- Test-first; no real pipeline/tool execution in tests (inject fakes per the
  existing `Executor` seam in `runner.py`).

## Open questions for the interview

- Ceiling policy: absolute cap (e.g. memory <= N GB, walltime <= T h) vs a multiple
  of the original request (e.g. <= 8x). And whether the ceiling is per-process or
  global.
- Progression: geometric (2x, 4x, 8x) capped at the ceiling, or jump-to-ceiling on
  the last attempt.
- What happens at the ceiling: give up with a clear "needs bigger box" message
  (never a false PASS) vs pause for human approval.
- Whether the scaled value is informed by the trace's peak RSS (already parsed into
  `RunRecord.resource_usage`) or purely multiplicative.
- Does this live only in the self-heal repair path, or also surface a structured
  `expected_signal` the verdict/report can show.
