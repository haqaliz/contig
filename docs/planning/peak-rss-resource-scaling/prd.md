# PRD — Peak-RSS-Informed Resource Scaling (OOM self-heal)

- **Slug:** `peak-rss-resource-scaling`
- **Type / branch:** feat · `feat/peak-rss-resource-scaling/aliz`
- **Capability:** C2 (self-heal breadth + auto resource-scaling), the explicitly-named
  "peak-RSS-informed scaling" pending slice (`docs/technical/CAPABILITY_ROADMAP.md:210-212`).
- **Source:** inline brief handed off from `contig-next` (no GitHub issue).
- **Deep dig:** `docs/planning/_card/understanding.md` (feasibility resolved).

---

## Problem Statement

When a pipeline task is killed for out-of-memory, Contig's self-heal retries it with a
**blind memory multiplier** — `bumped = int(current * 2)` (`self_heal.py:447-455`) — with
no reference to how much memory the task *actually* used. Consequences:

- **Slow convergence within a bounded budget.** A task that truly needs ~5× its request
  climbs 2×→4×→8× and can exhaust `max_attempts` (default 3, `self_heal.py:718`) or hit
  the 128 GB ceiling (`gave_up_at_ceiling`) *before* it lands — so a genuinely recoverable
  OOM is reported as an unrecoverable failure.
- **Over-allocation.** A task that needed only 10% more gets 100% more, wasting the user's
  compute (and, on managed/cloud backends, their money).

Unattended-completion rate is the headline Phase-1 reliability metric
(`docs/ROADMAP.md:101`, `CAPABILITY_ROADMAP.md:223`). Blind scaling leaves recoverable
failures on the table and produces no evidence about *why* a retry was sized as it was.

**For whom.** Every Contig persona hits OOM on real data — the lone computational
biologist (Persona A) and the wet-lab scientist who can't code (Persona B) most acutely,
because they cannot hand-tune resource directives themselves. The self-heal is the whole
value proposition for them.

**Evidence it's real.** OOM (`exit 137`) is the first, highest-priority failure class in
the detector (`detect.py:39-53`); the resource-aware ceiling work already shipped (v0.5.0)
precisely because this class matters. This slice completes that arc with evidence-based
sizing.

---

## Goals & Success Metrics

| Goal | Metric (testable) |
|---|---|
| Size the OOM retry to real usage | When the OOM'd task (or a same-process completed sibling) has a usable `peak_rss` in the partial trace, the retry request = `clamp(peak_rss × 1.5, current, ceiling)`, **not** `current × 2`. Asserted by unit test. |
| Recover more within the same budget | A fixture where the task needs ~5× and `max_attempts=3`: blind scaling gives up; peak-informed scaling lands in one retry and the run reaches PASS. |
| Never regress a working heal | When no usable observed peak exists (OOM'd row `peak_rss = -`/`0`, no completed sibling, or snakemake engine), behavior is **identical to today's blind multiplier**. Asserted by test. |
| Preserve safety invariants | Ceiling clamp and `gave_up_at_ceiling` give-up unchanged; never-shrink (`max(final, current)`) preserved. |
| Capture eval data | Every peak-informed retry records observed-peak, requested target, and which fallback tier fired into `RepairStep.detail`; surfaced in `repair_history` + `repair_progress.jsonl`. |

Non-goal metric: we do **not** claim a specific % lift in unattended-completion here (no
labeled OOM benchmark exists yet); the corpus telemetry this slice adds is what makes such
a measurement possible later.

**The telemetry is a first-class deliverable, not decoration.** It is the instrument that
tells us *whether sizing even fires on real OOMs* — i.e. how often a signal-killed task
carries a usable `peak_rss` (tier a), how often we're rescued by a completed sibling
(tier b), and how often we fall through to blind scaling (tier c). If tier c dominates in
the field, the honest win lives in tier b and the next slice re-orders the ladder. Logging
which tier fired to `RepairStep.detail` is what will surface that.

---

## Requirements

### Must-have

1. **Peak-informed sizing helper (pure, testable).** A new function that takes the failed
   run's `events` (to find the OOM'd task by `exit == 137`), the parsed partial trace
   (`list[TaskResource]`), the current memory request, the ceiling, and the safety factor,
   and returns either a sized absolute memory target (GB) **or** `None` (→ fall back).
   Pure `(inputs) → target | None`, no I/O, so it is unit-tested without a run.
2. **Fallback ladder (full).**
   a. OOM'd task's own `peak_rss_mb` (matched via `exit==137` `TaskEvent.process`/`name`
      joined to `TaskResource`), if `> 0`. **When more than one task OOM'd in the partial
      trace, use the max observed peak among them** — the resource patch bumps
      `process.resourceLimits` globally (`nfconfig.py:62-68`), so it must satisfy the
      hungriest OOM'd task.
   b. else max `peak_rss_mb` over **same-process** `COMPLETED` rows in the partial trace.
   c. else `None` → the existing blind multiplier path runs unchanged.
   A `peak_rss` of `0.0`/absent is treated as **unknown**, never as "0 MB"
   (`events.py:51-55`).
3. **Sizing formula.** `target_gb = min(ceiling, max(ceil(peak_mb/1024 × FACTOR), current))`.
   `FACTOR = 1.5`, a module constant, code-overridable (mirroring `resource_ceiling`).
   Binary GB (1 GB = 1024 MB, matching the parser and Nextflow `MemoryUnit`). **A sized
   target below the current request is expected and fine** (e.g. an 800 MB peak → 2 GB vs
   the 8 GB default): never-shrink holds it at `current`, so the retry is never *worse*
   than today. This is an acceptance case, not a bug.
4. **Integration at the OOM patch site** (`self_heal.py:974`, safe path): parse
   `run_dir/trace.txt` (already-imported `parse_resource_usage_file`, `self_heal.py:27`),
   compute the target, and apply it — feeding the sized target into the patch rather than
   threading `run_dir` into the pure `apply_patch`. When the helper returns `None`, the
   patch is applied exactly as today.
5. **Telemetry into `RepairStep.detail`** on the `patched_and_retried` step (975-979):
   observed peak (or "unavailable"), the fallback tier used, and requested-vs-current.
6. **Invariants preserved:** ceiling clamp, never-shrink, `gave_up_at_ceiling` pre-check
   (`_resource_ceiling_block`, 404-413/965), `max_attempts` bound.

### Should-have

- A clear `RepairStep.detail` string humans can read in `contig show` / the dashboard
  repair timeline ("scaled to 12 GB from observed peak 7.8 GB ×1.5").

### Nice-to-have (explicitly deferred — see Out of Scope)

- Walltime symmetry; corpus-schema capture; peak_vmem; cross-run learned priors.

---

## Technical Considerations

- **Seam.** Compute the target at `self_heal.py:974` where `run_dir` and
  `exc.record.events` are in scope. Keep `apply_patch` pure; either (i) add a resource
  `set` operation the safe path constructs with the sized target, or (ii) pass an optional
  `observed_target_gb` through the resource branch. Tech-plan decides; both keep the
  never-shrink/ceiling math in one place.
- **`peak_rss` is emitted.** `generate_nextflow_config` writes no `trace {}` block
  (`nfconfig.py:49-101`), so `-with-trace` uses Nextflow's default fields, which include
  `peak_rss`/`%cpu`; the parser resolves columns by header name (`events.py:117-134`). The
  feature is not inert.
- **Trace is on disk at heal time.** Executor guarantees `run_dir/trace.txt` on return
  (`runner.py:123-125`); `resource_usage` on the record is still `[]` until `_finalize`
  (`self_heal.py:1052-1054`), so the loop must parse the trace itself.
- **Reproducibility / verification impact:** none to the verdict. This changes only the
  *magnitude* of an auto-applied resource patch, already captured in the launch manifest
  and `repair_history`; `rerun`/`resume` re-derive from the same trace. No new
  `FailureClass`, no exit-code change, no raw-read egress.
- **Determinism/CI:** fully covered by injected trace/executor fixtures; no real pipeline
  run (consistent with the whole self-heal test suite).

---

## Risks & Open Questions

| Risk | Mitigation |
|---|---|
| Nextflow writes `peak_rss = -` on a signal-killed row (unverified in code) | Full fallback ladder: same-process completed sibling, then blind multiplier. Treat 0/absent as unknown. Tested both ways. |
| Observed peak ≈ current cap for an OOM'd task, so ×1.5 barely moves | Intended: ×1.5 over a peak that *reached* the cap still exceeds current and clears never-shrink; when peak < current (mislabeled/sibling), never-shrink protects it. |
| Sizing threads state into the pure `apply_patch` | Compute target at the call site; keep `apply_patch` pure. Tech-plan picks the exact signature. |
| Snakemake has no `trace.txt` (`stats.json`) | Out of scope; helper returns `None` → blind fallback. No snakemake regression. |

---

## Out of Scope

- **Walltime / `time_limit` sizing** to observed `realtime_sec`. Symmetric follow-on slice.
- **Corpus-schema capture** (`FailureCase`/`failure_case_from_run`). Telemetry rides in
  `RepairStep.detail` only this slice.
- **Snakemake** peak sizing (`stats.json` parsing).
- **`peak_vmem`** or cross-run/learned resource priors.
- **Any verdict, exit-code, or `FailureClass` change.**

---

## Guardrail check (CLAUDE.md)

Layer 2 (self-heal), on the user's compute, deterministic, no raw-read egress, no Layer-1
drift, gets better with better models (a smarter model proposes better sizing over the same
telemetry). ✅
