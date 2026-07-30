# Understanding — heal-scenarios-catalog-coverage (C6 heal-guard breadth)

Phase 2 deep-dig note. Grounded in a full read of `heal.py`, `self_heal.py`, `repair.py`,
`detect.py`, `models.py`, the guard CLI, the shipped corpora, and the two prior scenario
slices' commits and plans. `path:line` cited inline.

---

## What the work is really asking

`src/contig/data/heal_baseline.json` freezes **9 scenarios over 7 classes**. `repair.py`
proposes a patch for **14** classes. The nine classes with a live repair strategy that no
scenario ever drives through the real loop are the subject of this slice. `cli.py:2681-2695`
already names exactly those nine in the `heal-guard` docstring's honest-scope contract, so
the gap is documented in code, not just in the roadmap (`CAPABILITY_ROADMAP.md:1057`).

The premise held up: **all nine are reachable end-to-end, and driving them exposes real
defects.** But the brief's guess about *which* ones would be hard was wrong in both
directions, and the dig turned up a larger finding that reframes the slice.

---

## ⚠️ The main finding: five of the nine "repairs" are inert

The loop records a repair, sets `patch_applied=True`, retries, and reports success — while
the patch's stated operation is performed by **nothing**.

**Correction (post-implementation): they are inert for two different reasons, and flattening
them into one was wrong.** Four are `kind="env"` patches, whose operation `apply_patch`
merges into `target.backend_options` as strings (`self_heal.py:583-586`) while
`nfconfig.py:71-98` reads only `queue`/`region`/`partition`/`account`/`qos`/`time` — so every
other key is written and never read. `container_unavailable` is different: its patch is
`kind="retry"` (`repair.py:48-50`), for which `apply_patch` is a **documented** no-op, so the
promised `wait_seconds: 15` never reaches `backend_options` at all. The shipped `cli.py`
docstring keeps this split; so should any future write-up.

| Class | Patch operation | Kind | What actually happens |
|---|---|---|---|
| `disk_full` | `{"clean_work_dir": True}` (`repair.py:145`) | `env` | Nothing deletes the work dir. The key appears **only** at `repair.py:145`. No `statvfs`, no space check. |
| `permission_denied` | `{"fix_permissions": True}` (`repair.py:169`) | `env` | No `chmod`/`chown` anywhere. Key appears only at `repair.py:169`. |
| `conda_solve_failed` | `{"relax_or_pin_env": True}` (`repair.py:123`) | `env` | Nothing relaxes or pins any env spec. |
| `platform_unsupported` | `{"use_native_arch_backend": True}` (`repair.py:109`) | `env` | `target.backend` is **not** changed, so the approved retry re-runs on the same unsupported host — while the patch's own rationale says *"Re-running here won't help"*. |
| `container_unavailable` | `{"retry": True, "wait_seconds": 15}` (`repair.py:50`) | **`retry`** | `apply_patch` is a documented no-op for retry patches, so the promised 15-second wait is silently dropped and the fix degenerates to the bare re-run. **The weakest of the five** — a bare retry is a legitimate fix for a transient runtime outage, so only its *decorative field* is dishonest, not its whole premise. |

For contrast, the four that do something real: `missing_reference` merges a param that
reaches the re-run argv (`self_heal.py:575-582` → `runner.py:1118-1119`);
`reference_not_bgzf` actually decompresses (`self_heal.py:754-835`); `container_pull_failed`
and `download_failed` are honest `retry` no-ops where *the re-run itself is the fix*
(documented at `self_heal.py:549`).

**Why this matters for this slice.** A scenario declaring
`expected_outcome: "approved_and_retried"`, `expected_patch_applied: true`,
`expected_recovered: true` for `disk_full` would freeze into CI the claim *"Contig cleaned
the work directory and recovered the run."* Nothing was cleaned. The retry succeeded only
because the scripted executor was told to return 0. That is the **same family of
over-claim** v0.49.0's `patch_applied` slice just fixed (a rejected patch reported as
`Repaired`, `CHANGELOG.md:11`) — one layer further in: the flag is now honest about
*enactment*, but enactment of an inert operation still reads as a repair on every surface.

This is a decision the PRD must make explicitly, not a detail. It is also exactly the kind
of defect the slice was picked to find, and it is a **grounded C2 work-list** rather than a
guessed one.

---

## Scriptability, per class (corrected against the brief)

The driver injects exactly three seams — executor, index-builder, poll — and leaves the
detector and `propose` real (`heal.py:117-124`, the standing R2 contract). A scenario
controls only `(status, exit, log_text)` per attempt, plus `auto_approve`, `poll_decision`,
`resource_ceiling`, `index_builder_result`, `max_attempts`, `assay`, `qc_artifact`
(`models.py:539-577`).

**EASY — log text alone (7 of 9):** `missing_reference`, `container_pull_failed`,
`container_unavailable`, `conda_solve_failed`, `download_failed`, `disk_full`,
`permission_denied`.

The brief guessed `disk_full` and `permission_denied` would need filesystem fixtures. They
do not — and the reason is the finding above: **nothing measures disk space or touches
permissions**, so a genuinely full volume or a chmod-000 path would add nothing. A fixture
there would be theater.

**HARD — `reference_not_bgzf`.** Detection is log-only, but every heal outcome past the
first guard needs `params["fasta"]` pointing at a real plain-gzip file
(`self_heal.py:783-810`). `HealScenario` has **no `params` seam** and `heal.py:138` never
passes one, so through the driver the only reachable outcome is
`reference_recompress_unresolvable` ("No FASTA in params to recompress"). Options: freeze
the unresolvable path honestly, or add an optional fixture field on the qc_artifact
precedent (`models.py:563-569` — a *named fixture directive*, never an injected result).

**HARD — `platform_unsupported`.** `detect.py:355` requires a failed event with
`exit is None`, i.e. a trace row whose exit column is `-` (`events.py:91`). But
`AttemptSpec.exit` is a required `int` (`models.py:543`) and `heal.py` uses that one field
twice — as the trace column (`:62`) and as the executor's return code (`:82`). `None` cannot
be expressed, so the class falls through to `tool_crash` (confidence 0.4). Reaching it needs
an additive model/driver change (optional exit, or a separate trace-exit), which per the
prior slices' rule is a **mechanism** change, not a scenario change. A bespoke test in
`tests/test_self_heal.py` can already do it with a hand-written executor.

---

## Two traps that will silently break `outcome_match_rate == 1.0`

1. **Needle theft.** `diagnose_failure` is first-match-wins over ~20 branches
   (`detect.py:62-402`). The `oom` rule sits at position 2 and its needles include the bare
   substrings `"killed"` and `"oom"` (`detect.py:90`), so *any* realistic log line mentioning
   a kill collapses to `oom`. `no_progress` outranks even that (`detect.py:76`).
   Class-specific collisions: `permission_denied` (#5) steals Docker's
   `permission denied … docker.sock` from `container_unavailable` (#6); `container_pull_failed`
   (#7) steals `no matching manifest` from `platform_unsupported` (#18); `download_failed`
   (#8) steals `Temporary failure in name resolution` from `conda_solve_failed` (#9);
   `missing_index` (#10) steals any absence line naming an index from `missing_reference`
   (#16). Prior slices committed to this as a rule: a new scenario must be **discriminating
   against every line already frozen** (`plan_20260725.md:262-263`), and that check is O(n²)
   across what will be ~16-18 lines.
2. **The 30-minute poll.** For any gated (`needs_confirmation`) class, a scenario that sets
   neither `auto_approve` nor `poll_decision` falls back to the **real** file poll
   (`heal.py:101-115`) with the default `approval_timeout=1800` (`self_heal.py:959`) — the
   suite would hang for half an hour per scenario. Six of the nine are gated.

Also: `_is_ambiguous` is always False for these nine (single candidate, confidence ≥ 0.7), so
the choice branch and the outcomes `chose_and_retried` / `invalid_choice_rejected` are
**unreachable** here (`self_heal.py:278-285`). And `heal.py:159` computes `recovered` with
`any(...)` over all steps, so `recovered` and the *last* step's `patch_applied` can honestly
disagree on a multi-attempt give-up.

---

## What a scenario slice must also touch (from the two prior slices)

`tests/test_heal_scenarios.py` hard-asserts `report.total == 9`, `healed == 5`,
`recovery_rate == 5/9`, `baseline.scenario_count == 9`, and the exact-count
`len(baseline.covered_classes) == 7` (`:437-486`) — so `uv run pytest` fails before
`heal-guard` does. The baseline is refrozen with `uv run contig heal-guard
--update-baseline`, never hand-edited (`cli.py:2664`, `cli.py:2728-2743`), which also appends
a snapshot to `heal_history.jsonl`. `cli.py:2681-2695`'s honest-scope docstring must be
corrected in the same slice, taking the code as ground truth. Guarded numbers are never
loosened to accommodate a scenario; `recovery_rate` is informational-only and never guarded.

---

## Open questions for the PRD interview

1. **The inert-repair problem.** Freeze the loop's current behavior as-is (guarding a
   fiction), freeze only the honest give-up paths for those classes, or fix `repair.py`
   first? This is the central decision of the slice.
2. **Scope of the two HARD classes.** Add the additive fixture/exit seams (mechanism work,
   the qc_artifact precedent says it is legitimate when it does not bypass the code under
   test), or freeze `reference_not_bgzf` at its `unresolvable` path and drop
   `platform_unsupported` with the reason recorded?
3. **Recovery vs give-up shape.** Per class, freeze the recovering path, the give-up path, or
   both? Both doubles the corpus and the O(n²) discrimination burden.
4. **`recovery_rate` will move again** — it is informational, but its trend was already
   declared non-comparable at v0.49.0. Say so, or reset the series?

---

## Guardrail check (`CLAUDE.md`)

Layer 2 throughout — this is the run/self-heal/verify harness and its evaluation data, the
stated moat (constraint #2). No Layer-1 workflow generation. No wet-lab, clinical, or
proprietary-data dependency. Inside the founder's edge.
