# PRD: Bounded resource-aware self-heal retry

**Slug:** `resource-aware-retry` · **Branch:** `feat/resource-aware-retry/aliz` ·
**Owner:** aliz
**Origin:** First slice of capability **C2** (self-heal breadth + auto
resource-scaling), `docs/technical/CAPABILITY_ROADMAP.md:94-124`. Selected by
`contig-next` after v0.4.0 closed C1's turnkey follow-on.

---

## Problem Statement

When a pipeline process fails out-of-memory (`oom`) or exceeds its walltime
(`time_limit`), Contig's self-heal loop already retries with a doubled resource
request. But that scaling is **unbounded**: `apply_patch`
(`self_heal.py:259-300`) multiplies the carried-forward `ExecutionTarget`
resource limits each attempt with **no ceiling**. There are two failure modes:

1. **Runaway scaling** — nothing caps how large memory/time can grow, so a
   pathological process could be retried with an absurd request (e.g. 256 GB on a
   64 GB node), wasting the retry budget and the node.
2. **Pointless terminal retries** — when scaling can't fix the failure (the job
   genuinely needs a bigger box than exists), the loop burns its remaining
   `max_attempts` re-running ever-larger requests, then reports a generic failure
   with no honest "this exceeds what auto-scaling can do" signal.

Neither behaviour is dangerous to correctness (the verdict never falsely passes),
but both waste compute and degrade the headline reliability metric —
**unattended-completion rate** (`ROADMAP.md:101`, `CAPABILITY_ROADMAP.md:100-102`)
— and neither produces the *structured, rationale-bearing scaling record* that is
part of the moat (`FEATURES.md:64`, Terra row: incumbents do mechanical resubmit
with no reasoned patch).

**Evidence it's real:** OOM is one of the named top-5 failure modes from Phase 0
(`ROADMAP.md:56`); resource-aware retry is the *first* item under C2's "what we
build" (`CAPABILITY_ROADMAP.md:105-108`), explicitly "scaled memory within a
bounded ceiling" + "a bounded retry budget so auto-scaling can never loop without
converging."

---

## Goals & Success Metrics

| Goal | Measure |
|---|---|
| Scaling can never exceed a ceiling | A run that would scale past the cap is clamped to the cap; asserted by test. |
| The auto-scale loop provably terminates | A test injecting persistent OOM proves the loop stops (no infinite re-scale) and returns a record, within `max_attempts`. |
| Honest terminal outcome at the ceiling | When the process still fails at the cap, the run gives up with a distinct, named outcome and an honest FAIL verdict — never a false PASS. |
| Recovered + unrecovered cases are captured | Each scaling attempt continues to land in `repair_history` and the pending corpus, now labelled with the scaling/ceiling state (moat #2 fuel). |

This is reliability/quality hardening, not a user-facing growth metric; success is
the tests above passing and the existing self-heal suite staying green.

---

## User Personas & Scenarios

- **Persona A (lone computational biologist)** kicks off a germline run unattended
  overnight on a workstation. A variant-calling step OOMs. Contig scales memory
  16→32→64 GB, succeeds, and the morning verdict shows the reasoned scaling chain.
- **Persona A, the hard case:** the step needs more memory than the 128 GB node
  has. Contig scales to the 128 GB cap, fails again, and **stops** with a clear
  "OOM persists at the 128 GB ceiling; this needs a bigger node" message instead of
  thrashing. The biologist knows exactly what to do next (bigger box), not "it
  broke."
- **Core facility (C):** wants throughput and predictable resource use; an
  unbounded auto-scale that could request 512 GB is an operational risk a ceiling
  removes.

---

## Requirements

### Must-have

- **M1 — Absolute resource ceiling.** Memory and time scaling are capped at
  absolute defaults (`CEILING_MEMORY_GB = 128`, `CEILING_TIME_H = 72`), defined as
  module-level constants and passed into the scaling path as parameters
  (overridable in code; no new CLG flags this slice). Scaling never produces a
  value above the cap.
- **M2 — Clamp at the ceiling.** When the next multiply would exceed the cap, the
  applied value is **clamped to the cap** (not the over-cap product), and the run
  is attempted once at the cap.
- **M3 — Give up honestly at the ceiling.** When a process fails OOM/time_limit
  while already at the cap (i.e. clamping can grow it no further), the loop stops
  scaling and records a distinct terminal outcome (e.g. `gave_up_at_ceiling`) with
  a clear message naming the resource and the cap. The verdict is the honest
  unrecovered result (FAIL), **never a false PASS / UNVERIFIED-as-PASS**.
- **M4 — Provable termination.** A test injecting persistent OOM proves the
  auto-scale loop terminates within the existing `max_attempts` bound and returns a
  `RunRecord` — no infinite re-scale.
- **M5 — Structured record.** Each scaling attempt's `RepairStep` (and the patch's
  `expected_signal`/rationale) reflects the scaling state — scaled, clamped to
  ceiling, or gave-up-at-ceiling — so `repair_history`, the JSONL live feed, and
  the corpus label the scaling path. Recovered and unrecovered cases continue to be
  stashed to the pending corpus exactly as today.

### Should-have

- **S1 — Ceiling applies to both `memory` and `time`** symmetrically (the
  `time_limit` repair is in scope, not just OOM).
- **S2 — A clamp that lands the value exactly on the cap** in the Nextflow literal
  format already used (`"128.GB"`, `"72.h"`), so `nfconfig.py:59-68` emits a valid
  `process.resourceLimits`.

### Nice-to-have (explicitly deferred — see Out of Scope)

- Peak-RSS-informed scaling (target the measured need rather than a blind 2×).
- CLI flags / `ExecutionTarget` persistence for the ceiling.

---

## Technical Considerations

**Insertion point.** The ceiling is enforced in `apply_patch`
(`self_heal.py:259-300`), which already owns the numeric mutation
(`_lead_number(...) * factor` → `"{n}.GB"`/`"{n}.h"`). It gains a ceiling parameter
(default from the new constants) and clamps the computed value. The declarative
`Patch.operation` (`{"multiply": {...}}`) stays unchanged in `repair.py:16-35`;
the policy lives where the numbers are applied. The self-heal loop
(`self_heal.py:303-514`) threads the ceiling through and detects the
"already-at-ceiling and still failing" condition to emit the terminal outcome.

**Termination.** The loop is already bounded by `max_attempts=3`. The new
guarantee is that scaling itself can't cause a non-converging loop: once a value is
clamped to the cap, a subsequent same-class failure yields `gave_up_at_ceiling`
rather than another (no-op) scale.

**Reproducibility/verification impact.** No change to the verdict-reduction
guarantees: an unrecovered run is FAIL, as today. The scaling decisions are
recorded in `repair_history` and the bundle, which *strengthens* the auditable
trail (a reader can see exactly how far Contig scaled and why it stopped). No
raw-read egress. No model/serialization change required if the scaling state fits
the existing `RepairStep.outcome: str` (to be confirmed in tech-plan — a new field
is allowed only if `outcome` can't carry it cleanly).

**Testing.** Strict TDD with the injected `Executor`
(`runner.py:72`, `Callable[[list[str], Path], int]`). A fake executor simulates
OOM-then-success (recovery path) and persistent-OOM (ceiling/give-up path) across
attempts by returning exit 137 and writing canned logs. **No real Nextflow or tool
execution, no network.** Mirrors `tests/test_self_heal.py` / `tests/test_runner.py`
patterns.

---

## Data Model / Contracts

- Scaling values remain Nextflow literals in `ExecutionTarget.resource_limits`
  (`"<n>.GB"`, `"<n>.h"`), keys `memory`/`time` (`nfconfig.py` keys are
  `memory`/`cpus`/`time`).
- New constants: `CEILING_MEMORY_GB = 128`, `CEILING_TIME_H = 72` (module-level,
  parameterized into the scaling functions).
- A terminal outcome label (`gave_up_at_ceiling` or equivalent) added to the
  vocabulary of `RepairStep.outcome`. No new `FailureClass` (detection is
  unchanged).

---

## Risks & Open Questions

- **R1 — `outcome: str` vs a typed field.** Whether the scaling state fits the
  existing free-form `outcome` string or warrants a small typed addition to
  `RepairStep`. Resolve in tech-plan; prefer the minimal change.
- **R2 — Default cap values.** 128 GB / 72 h are reasonable defaults but unvalidated
  against real partner hardware. They are code-overridable, so this is low-risk;
  revisit when a design partner's node sizes are known.
- **R3 — Interaction with a pre-set ceiling below the current request.** If a run's
  *original* request already exceeds the cap, clamping must not *shrink* a working
  request on a non-resource failure. Mitigation: the ceiling only bounds the
  *scaled* value on an `oom`/`time_limit` patch; it never reduces a limit on
  unrelated patches. Cover with a test.
- **R4 — Dashboard surface.** Showing the new terminal outcome in the dashboard
  repair-chain view is **out of scope** for this slice (the data lands in
  `repair_history`/JSONL; rendering is a follow-on if desired).

---

## Out of Scope (explicit)

- **Peak-RSS-informed scaling.** Deferred: `resource_usage` is only populated at
  `_finalize()` (`self_heal.py:541`), after the patch decision; targeting the
  measured peak needs a refactor (populate `exc.record.resource_usage` before
  raising, or parse the trace at catch time). Named follow-on, not this slice.
- **CLI flags** (`--max-memory-ceiling` etc.) and **`ExecutionTarget` persistence**
  of the ceiling. Built-in code-overridable defaults only.
- **New failure classes / repair strategies** (missing-index, reference/build
  mismatch, format conversion, pin conflict) — those are later C2 slices, not this
  one.
- **Detection changes.** `oom`/`time_limit` detection (`detect.py:42-64`) is
  unchanged.
- **Dashboard rendering** of the new outcome.

---

## Guardrails check (CLAUDE.md)

Layer 2 only (run + self-heal). No Layer-1 workflow authoring. No raw-read egress.
Self-heal stays bounded and logged; the new ceiling makes the bound stronger. Gets
better as base models improve (a smarter diagnoser still flows through the same
bounded scaling). Test-first.
