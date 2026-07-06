# Understanding — peak-rss-resource-scaling (Phase 2 deep dig)

Synthesized from two read-only mapping agents + a direct config check. All refs are
`src/contig/*` in this worktree; line numbers exact at dig time.

## What the work really asks

Replace the blind memory multiplier in the OOM self-heal with an **evidence-based**
retry: size the memory bump to the failed task's **observed peak memory**
(`TaskResource.peak_rss_mb`) parsed from the run's partial `trace.txt` at heal time,
falling back to the existing blind multiplier when no usable observed peak exists.
Layer 2, deepens unattended-completion, captures richer eval data.

## Feasibility — RESOLVED (the make-or-break checks)

1. **`peak_rss` IS emitted on real runs.** `nfconfig.py:49` `generate_nextflow_config`
   writes **no `trace {}` block**, so `-with-trace <path>` (`runner.py:230`) uses
   Nextflow's *default* trace field set, which includes `peak_rss` / `%cpu`. The parser
   `events.parse_resource_usage_file` (`events.py:106-142`) resolves columns by header
   *name*, so it reads them regardless of order. → The feature is **not inert**.
2. **The trace is on disk at heal time.** The executor guarantees `run_dir/trace.txt`
   exists when `run_pipeline` returns (`runner.py:123-125, 270`); the heal loop has
   `run_dir` in scope (`self_heal.py:737`) and already imports
   `parse_resource_usage_file` (`self_heal.py:27`). `_finalize` reads the same path
   (`self_heal.py:1052-1054`) — but only at finalize; `exc.record.resource_usage` is
   still `[]` at heal time. We parse it ourselves at the patch site.
3. **The OOM'd task is identifiable.** `Diagnosis` (`models.py:228-234`) carries no
   task name — only `failure_class`, `evidence` (free-text). But `exc.record.events`
   (`self_heal.py:771`) holds `TaskEvent{process, name, status, exit, is_failure}`
   (`models.py:107-115`); the OOM'd task is the `exit == 137` event
   (`detect.py:42`), joined to the `TaskResource` row by `process`/`name` (shared,
   `models.py:126-127`).

## The exact seam

- OOM is a **safe** patch (`repair.py:16-25`, `operation={"multiply":{"memory":2}}`),
  so it bypasses the gated branches (829/871/922) and is applied on the **safe path at
  `self_heal.py:974`**, then recorded as `RepairStep(outcome="patched_and_retried")`
  (975-979, `detail` currently unset).
- `apply_patch` (`self_heal.py:416-475`) is **pure** — only `target, patch, params,
  ceiling`; no run_dir. The memory math is 447-455: `bumped = int(current*mult)`,
  `capped = min(bumped, ceiling)`, `final = max(capped, int(current))` (**never-shrink**),
  written as `f"{final}.GB"`.
- Ceiling give-up pre-check `_resource_ceiling_block` (404-413, called at 965) →
  `gave_up_at_ceiling`. Loop bound = `max_attempts` (default 3, `self_heal.py:718`).

**Design implication:** compute the peak-informed target *at line 974* (where `run_dir`
+ `events` are in scope) and feed it into the patch, rather than threading run_dir into
the pure `apply_patch`. Keep the ceiling clamp + never-shrink + `gave_up_at_ceiling`.

## Open questions for the PRD interview (design decisions, not code facts)

1. **Safety factor.** Target = `observed_peak × factor`. Default factor? (e.g. 1.5×.)
2. **Fallback ladder when the OOM'd row lacks a usable peak.** A signal-killed task's
   own `peak_rss` may be `-` → parser yields `0.0` (**must treat 0/absent as "unknown,"
   not "0 MB"**, `events.py:51-55`). Ladder: (a) OOM'd task's own peak → (b) max peak of
   *same-process* completed rows in the partial trace → (c) blind multiplier (today's
   behavior). Confirm the ladder + that (c) never regresses a working heal.
3. **Never-shrink interaction.** For an OOM-killed task, observed peak ≈ the cgroup cap
   ≈ current request, so `peak × factor (≥1)` exceeds `current` and survives
   `max(capped, current)`. If observed peak < current (mislabeled/sibling row), the
   never-shrink rule protects it. Confirm this is the intended semantics.
4. **Engine scope.** Nextflow only. Snakemake's artifact is `stats.json`
   (`runner.py:260`), which the TSV parser doesn't read → snakemake falls back to the
   blind multiplier. Confirm scope = Nextflow-only this slice.
5. **Walltime (`time_limit`) symmetry.** Brief says "OOM/walltime." `realtime_sec` is in
   the same trace. Scope decision: memory-only this slice, or also size walltime to
   `observed_realtime × factor`? (Recommend memory-first; walltime as a stated
   follow-on, unless cheap to include.)
6. **Eval-data capture depth.** Minimal: put observed-peak-vs-requested + which fallback
   fired into `RepairStep.detail` (free-text `str | None`, no model change). Deeper:
   extend `FailureCase`/`failure_case_from_run` (`corpus.py:107-129`) with the observed
   peak. Confirm slice depth.

## TDD fixtures to extend (from the dig)

- `tests/test_self_heal.py:105-125` `test_self_heal_populates_resource_usage_from_trace`
  — closest heal-path fixture (fake executor writes a trace with peak_rss=1228.8).
- `tests/test_resource.py` `_trace(...)` helper (header incl. `peak_rss %cpu`), MB/GB/KB
  + dash→0 + header-order-independence cases.
- `tests/test_events.py:19,38-77` — the `exit 137 / FAILED` trace-row fixtures (event
  level, no peak_rss column yet) → extend to assert peak-on-OOM'd-row behavior.

## Guardrail check

Layer 2 (self-heal), local, deterministic, no raw-read egress (reads the run's own
trace on the user's compute). No Layer-1 drift. ✅
