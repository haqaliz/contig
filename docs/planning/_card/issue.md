# Card — feat/repair-success-analytics/aliz

**Type:** feat · **Id (slug):** `repair-success-analytics` · **Owner:** aliz
**Source:** inline brief (no GitHub issue — `gh issue list` finds none related;
the only open issue, #33 "Flaky: reproduce freshness guard can report a false
UNVERIFIED", is unrelated).
**Selected by:** `/contig-next` on 2026-09-05, against v0.56.0 (`[Unreleased]` empty).

---

## Brief

Build the cross-run repair / unattended-completion analytic that `FEATURES.md:216`
leaves as *"cross-run aggregation still to build"* — the metric `docs/ROADMAP.md:109`
makes the Phase 1 → Phase 2 exit gate ("≥70% unattended completion on the core
pipeline") and that nothing in the CLI can currently compute.

Aggregate `repair_history` across every run record under `runs/` into
auto-healed vs human-declined vs gave-up, by failure class, following the shipped
`contig clusters` / `contig coverage` aggregation pattern (`cli.py:3673`, `:3707`)
and the outcome families already defined in
`docs/planning/repair-patch-applied/dashboard-repair-surface/spec.md`.

### Verified caveats (measured against the 15 real records in `runs/`, do not re-derive)

1. All **7** repair steps in the 15 real records on disk **predate v0.49.0 and carry
   no `patch_applied` key**. A naive aggregator reading the field would report 0%
   applied across the entire real corpus — exactly the over-claim the
   `patch-applied-field` slice existed to kill. The field must be **three-state**
   (applied / not-applied / unknown-legacy), counted separately, never collapsed
   into a single percentage.
2. One real record carries `outcome: "stopped_for_confirmation"` — the literal the
   dashboard spec correctly called **dead in `src/`**. Legacy data still has it, so
   the outcome map needs a legacy branch.
3. n=15 runs / 7 steps: the command must **lead with counts plus a thin-data flag**,
   not a headline rate.
4. This recovers nothing new for a user — it only makes the self-heal loop's field
   performance legible, and the output should say so.

### Observed shape of the real data (`runs/**/run_record.json`, n=15)

- `repair_history` steps: 7 total, across 15 records.
- Diagnosis classes present: `oom` ×2, `tool_crash` ×3, `missing_index` ×1, `unknown` ×1.
  (`failure_class` lives on `step.diagnosis`, **not** on the step itself — the step's
  own `failure_class` key is absent/None in every record.)
- Outcomes present: `patched_and_retried` ×2, `gave_up` ×4, `stopped_for_confirmation` ×1.
- `patch_applied` present: 0 / 7.
- Top-level `status` is None on all 15 records (status lives on the summary, not the
  record root) — confirm the real completion signal during the dig.

---

## Why this was picked (grounded citations)

- `docs/ROADMAP.md:109` — Phase 1 → Phase 2 gate: "≥70% unattended completion on the
  core pipeline". `docs/ROADMAP.md:101` — success metric: "Runs completed without
  human intervention: ≥70% of real runs". **Neither is computable today.**
- `FEATURES.md:216` — "Repair success-rate analytics | Across all runs: auto-healed vs
  paused vs gave-up, by failure class | Built data (the `patch_applied` slice supplied
  the missing field — proposed vs applied was previously indistinguishable, so any such
  analytic would have over-counted); **cross-run aggregation still to build** | M".
- `docs/technical/CAPABILITY_ROADMAP.md` (C2) — "Unattended-completion rate is the
  headline reliability metric (ROADMAP Phase 1)"; "Eval data captured: ... repair
  success-rate analytics gain new classes".
- `docs/technical/CAPABILITY_ROADMAP.md:617` — the inert-repairs revisit trigger commits
  to counting "the next 20 diagnosed failures appended to the pending corpus ... by
  grouping `runs/pending_corpus.jsonl` by `failure_class`, no new instrumentation" —
  currently a by-hand act this command would make checkable.
- Unblocked by v0.49.0 (`patch_applied`) and the inert-repairs slice (advisory /
  `gave_up` outcome taxonomy).

## Guardrails check (CLAUDE.md)

Layer 2 (the run/self-heal/verify loop's own telemetry) ✓. No Layer 1 ✓. No wet-lab /
clinical / proprietary data ✓. Deepens moat #2 (accumulated evaluation data becomes
legible rather than push-built and unmeasured) ✓. Read-only over existing artifacts —
no new instrumentation, per the roadmap's own revisit-trigger wording ✓.

## Ruled out as already shipped (verified in code, prose is stale)

- Runtime `reference_mismatch` detector — `CHANGELOG.md:243`, `models.py:269`,
  `detect.py:445` (its planning dir has only doc commits, which misleads).
- Dashboard repair surface — `dashboard/lib/derive.ts:41` now reads `patch_applied`.
- Reproduce dashboard card + DOI/PDF intake — both have `feat:` commits, though
  `CAPABILITY_ROADMAP.md` still lists them as standing C8 deferrals.

## Considered alternates (not this slice)

- **C8 M8 real-repo smoke** (`docs/planning/reproduce-env-alias-map/prd.md:112-116`) — a
  committed revisit trigger; 11 C8 slices have shipped without ever touching a real repo.
  Highest truth-value per hour, but a manual network gate, not a build slice.
- **C2 deferral (b)** — `risk="destructive"` is a no-op to the engine; nothing branches on
  it and `--auto-approve` has no carve-out (`self_heal.py:1379`, `:1442`), so only the
  dashboard honors it.
