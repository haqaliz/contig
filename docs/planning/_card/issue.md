# Card: feat/sibling-peak-rescue/aliz

**Source:** inline brief (no GitHub issue — `id` is a slug). Selected by
`contig-next` as the highest-leverage next feature; the worktree was started
from its handoff prompt.

**Owner:** aliz · **Branch:** `feat/sibling-peak-rescue/aliz`
(worktree `.claude/worktrees/feat-sibling-peak-rescue`, branched from
`origin/master` @ 7a8c0e3)

---

## Brief

Extend the shipped peak-RSS/walltime self-heal (CAPABILITY_ROADMAP C2) with the
**same-process sibling-peak rescue**: when the OOM'd/walltime-killed task's own
peak/realtime is censored (signal-killed, `-`/0, absent trace row) and the blind
`×2` fallback would fire, size the retry from the **max observed sibling value**
in the same coarse `process` (resourceLimits is process-global).

Prerequisite: fix the trace parser, which today sets `process == name` for every
row, to expose the real coarse `process` column — this has a `progress.py`
blast radius, so land that carefully.

Same two-tier honesty contract as the shipped slices: ceiling clamp,
never-shrink, `gave_up_at_ceiling`, observed values + tier recorded in
`RepairStep.detail`.

Optionally fold the observed peak into the `FailureCase` corpus schema
(currently rides in `detail` only).

Test-first with injected trace fixtures; Nextflow-only; no
verdict/exit-code/FailureClass change.

## Honest limits to carry into the writeup

- Push, not demand-pull: no design partner asked; organic frequency of the
  censored-peak case is unmeasured (no real Contig-launched run has produced it).
- No real Nextflow in CI — injected trace/executor fixtures only, per the
  parent slices' precedent.
- The `process == name` parser defect is a mechanism blocker the dig must
  verify against the actual parser code, not the roadmap prose.
- OOM/walltime heals are Nextflow-only today; Snakemake is out of scope.
- Blast radius: `progress.py` consumes the trace parser — the dig must
  enumerate the consumers before the plan.

## Guardrail check

Layer 2 (self-heal breadth for the shipped C2 resource-scaling ladder). No
Layer 1, no wet-lab/clinical dependency, no raw-read egress, no
verdict/exit-code/FailureClass change.