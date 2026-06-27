# Aspect spec: bounded-scaling

Single aspect of the `resource-aware-retry` feature (PRD:
`docs/planning/resource-aware-retry/prd.md`). The feature is cohesive enough to be
one aspect: add an absolute ceiling to the existing OOM/time_limit self-heal
scaling, clamp at it, and give up honestly when the relevant resource can grow no
further.

## Problem slice / user outcome

Today `apply_patch` (`self_heal.py:259-300`) scales `memory`/`time` with **no
ceiling**, and the loop has no "this resource can't grow any further" terminal
state. Outcome wanted: scaling is bounded by an absolute cap; at the cap a
recurring resource failure stops with a clear, honest `gave_up_at_ceiling` and a
FAIL verdict — never a false PASS, never an unbounded or thrashing retry.

## In-scope requirements (from PRD must/should)

- **Absolute ceiling** for `memory` (128 GB) and `time` (72 h), as module-level
  constants threaded as a parameter into the scaling path (code-overridable; no CLI
  flag).
- **Clamp** the scaled value to exactly the cap when a multiply would overshoot.
- **Never shrink** a pre-existing request that already exceeds the cap on the
  resource patch (R3).
- **Give up at ceiling**, per failure class: `oom` → memory at/above cap;
  `time_limit` → time at/above cap. Record a distinct `gave_up_at_ceiling` outcome
  with a human message naming the resource and the cap. Verdict = the honest FAIL.
- **Provable termination**: a persistent-OOM run terminates and returns a
  `RunRecord` (no infinite re-scale).
- **Capture**: the gave-up attempt continues to land in `repair_history` /
  `repair_progress.jsonl` / pending corpus, labelled with the new outcome.

## Out of scope (this aspect)

Peak-RSS-informed scaling, CLI flags, `ExecutionTarget` persistence of the ceiling,
new failure classes/repairs, detection changes, dashboard rendering. (All per the
PRD Out-of-Scope section.)

## Acceptance criteria (testable, TDD)

1. **Clamp-exact:** an OOM patch whose multiply would exceed the cap yields
   `resource_limits["memory"] == "128.GB"` exactly (and the `time_limit` analogue
   `"72.h"`).
2. **Never-shrink:** with memory already `"256.GB"` and an OOM, the memory limit is
   **not** reduced below 256 (it is at/above the cap → give up, limit unchanged).
3. **Recovery still works:** OOM-then-success across two attempts scales memory up
   (e.g. 8→16 GB), recovers, and records `patched_and_retried`; verdict is not FAIL.
4. **Give-up at ceiling:** a run starting at (or driven to) the cap with persistent
   OOM records `outcome="gave_up_at_ceiling"`, a `detail` message naming memory and
   128 GB, returns a `RunRecord`, and the verdict is FAIL — never PASS/UNVERIFIED.
5. **Termination:** the persistent-OOM scenario returns within the bounded attempts
   (no infinite loop); asserted by the test completing and the attempt count being
   bounded.
6. **time_limit symmetry:** the same give-up/clamp behaviour holds for `time_limit`
   at the 72 h cap.
7. **Corpus capture:** the gave-up case is appended to the pending corpus (existing
   `append_case` path) so the flywheel sees ceiling give-ups.
8. **Regression:** the full existing `uv run pytest` suite stays green (no behaviour
   change for non-resource patches or for runs that never reach the cap).

## Dependencies / sequencing

No external deps. Build order: (1) ceiling constants + clamp + never-shrink in
`apply_patch`; (2) `RepairStep.detail` field + at-ceiling give-up in the loop;
(3) wire the ceiling param through `self_heal_run`, plus regression. All in
`src/contig/`, tested via the injected `Executor` (no real Nextflow/tool/network).

## Open questions / risks

- **Message surface:** `RepairStep.outcome` is a label, not a sentence. Chosen
  approach: add `RepairStep.detail: str | None = None` (backward-compatible) for the
  human message. Confirm during RED that no existing field carries it more cleanly.
- **Default caps (128/72)** are unvalidated against partner hardware (PRD R2);
  code-overridable, so low risk.
