# Understanding — `auto-approve-attendance` (Phase 2 dig)

Source: `docs/planning/_card/issue.md`. Three read-only agents mapped the launch/replay
path, the `repair_stats` attendance axis, and the signing/back-compat cost. Every claim
below is cited; the two marked 🔴 were re-verified by hand in the main thread because
they contradict shipped code comments.

---

## What the work is really asking

`contig repair-stats` cannot say whether a human was in the loop, so runs land in an
`attendance_unknown` bucket that is excluded from **both** sides of the
unattended-completion rate (`repair_stats.py:274-282`). That rate is the Phase 1 → 2 exit
gate (`docs/ROADMAP.md:109`). Persist the fact; empty the bucket by evidence.

---

## 🔴 F1 — The premise is half wrong: `chose_and_retried` is already strictly attended

`repair_stats.py:88-91` states both `approved_and_retried` **and** `chose_and_retried`
"fire on a real human approval AND under `--auto-approve`". **False for the second.**

The `if auto_approve:` block at `self_heal.py:1442` always terminates the iteration —
`return _finalize(...)` at `:1466-1471` when `not cont`, else `attempt += 1; continue` at
`:1469-1470`. The ambiguous-choice gate that records `chose_and_retried`
(`default_outcome=` at `self_heal.py:1497`) sits at `:1472`, **below** that block, and is
therefore unreachable when `auto_approve is True`. The code says so itself at
`self_heal.py:1440-1441`: *"--auto-approve is non-interactive: it always takes the
best-ranked gated fix, so there is no choice to make even when ambiguous."*

Verified in the main thread by reading `self_heal.py:1436-1500` directly, not taken from
the agent report. Corroborated by the only test that produces the literal,
`tests/test_self_heal.py:3578-3589`, which injects an interactive `poll` and leaves
`auto_approve` at its default `False`.

**Consequences.**
1. `chose_and_retried` belongs in `ATTENDED_OUTCOMES` **today**, independent of this
   feature. That is a standalone correctness fix and it should not be smuggled in as a
   side effect of persisting a flag.
2. The predecessor slice's PRD is wrong on the same row
   (`docs/planning/repair-success-analytics/prd.md:344`), as is the shipped comment. Both
   need correcting, or the next reader re-derives the same error.
3. **It halves what this feature buys.** Only `approved_and_retried` is genuinely
   two-moded — Site A `self_heal.py:1449` (auto-only) and Site C `self_heal.py:1553`
   (interactive-only, gated on a human `decision == "approve"`). Those two sites are
   mutually exclusive on the flag, so a persisted run-level `auto_approve` resolves that
   literal **completely**, with no residual ambiguity.

## 🔴 F2 — A pre-existing over-claim that is larger than the feature

`_apply_patch_and_maybe_build` returns its **own** outcome and discards `default_outcome`
for `build_index` / `recompress_reference` patches (`self_heal.py:1085-1088`, `:1157`).
Verified by hand at `self_heal.py:1080-1157`.

So a human who approves a gated index build at Site C records
`built_index_and_retried` — which is in `APPLIED_OUTCOMES`, falls to the else branch of
`classify_attendance` (`repair_stats.py:177`), and is classified **`unattended`**.
`_run_is_attended` (`repair_stats.py:198-207`) then reads that run as unattended and
counts it in the **numerator** of the gate metric.

Attendance derived from step-outcome literals is structurally leaky: the literal records
*what the machine did*, not *who decided it*. This argues for deriving run-level
attendance from the persisted run-level flag rather than from the literals — a scope
question the PRD must answer explicitly rather than inherit.

## F3 — Where the field goes: not the balanced trade the brief assumed

The card (`_card/issue.md:38-53`) presents `LaunchManifest` vs `RunRecord` as a genuine
trade. The dig shows it is lopsided.

| | `LaunchManifest` | `RunRecord` |
|---|---|---|
| Signing cost | **Zero** — `launch.json` appears nowhere in `signing.py` or `bundle.py`; not in the attested payload list (`bundle.py:104-113`) | **Fifth disclosed break, widest class** |
| Replay risk | **Near zero by construction** | n/a |
| Precedent | `harmonized_reference` (`models.py:436`) — written `cli.py:785`, read by **no** replay path | `sex_inference` comment template (`models.py:359-363`) |

- **The replay objection largely dissolves.** Replay is a hand-written, per-field mapping
  at three call sites (`cli.py:878-901` rerun, `cli.py:2548-2571` resume,
  `dashboard/lib/runs.ts:667-700`). There is no `**model_dump()` anywhere, so a new
  manifest field is **inert until someone writes the line**. The residual risk is a future
  editor adding it out of symmetry — the way `assay` was wired into `rerun` (`cli.py:881`)
  but forgotten in `resume`. Mitigation is a docstring in the `models.py:433-434` voice
  saying *recorded for attendance, NOT replayed*.
- **`RunRecord` is the worst case of its class.** `canonical_record_bytes` is a full
  `record.model_dump(mode="json")` with no exclusions (`signing.py:63-64`), so a
  top-level field is emitted for **every** record: blast radius 100% of signed bundles,
  with none of the empty-list narrowing that made the `patch_applied` break defensible
  (`CHANGELOG.md:1002-1004`). The `exclude_none` fix is explicitly foreclosed
  (`CHANGELOG.md:1606-1609`).
- The counter-precedent (D4, `CHANGELOG.md:1286-1291`) argues against persisting
  *host-dependent* runtime knobs. `auto_approve` is not host-dependent — it is a property
  of how this run was decided, the same category as `allow_reference_mismatch`.

**Leaning: `LaunchManifest`, as write-only provenance on the `harmonized_reference`
precedent.** To be confirmed at the PRD gate.

## F4 — The trap that would empty the bucket by fiction

`LaunchManifest` is a plain `BaseModel`. A field declared `auto_approve: bool = False`
makes pydantic resurrect an absent key as `False`, so **every legacy bundle silently
becomes "a human was there"** — the bucket empties without evidence. This is exactly the
`patch_applied` defect, whose cost `repair_stats` is still paying via the only
double-read in the codebase (`repair_stats.py:138-147`, `:313-318`).

Required: `bool | None = None` (precedent `HealScenario.expected_patch_applied`,
`models.py:602-605`), or a raw-key-presence read. Absent must stay distinguishable from
recorded-`False`.

## F5 — Empirical: nothing moves retroactively, and the loader must tolerate absence

All 15 real bundles carry **no `launch.json` at all** (`find` over
`/Users/aliz/dev/at/contig/runs` → 0 hits). They are dated 2026-06-21..23 and
`LaunchManifest` was introduced 2026-06-22 (`a4b4b66`), so the corpus **predates the
manifest**. This clears the manifest of any write-coverage suspicion — but it means:

- The reported 64.3% does **not** move. Every existing bundle stays unknown-attendance.
- The real corpus contains only `patched_and_retried` ×2, `gave_up` ×4,
  `stopped_for_confirmation` ×1 — **zero** `approved_and_retried` steps. So
  `attendance_unknown` is **0 today** (`prd.md:414-425` predicted and confirmed this).
  **The feature does not empty a full bucket; it stops a currently-empty bucket from ever
  filling.** That reframing must survive into the writeup — the card's "empty the bucket"
  wording overstates it.
- Every test fixture in both test files writes only `run_record.json`
  (`tests/test_repair_stats.py:474-490`, `tests/test_cli_repair_stats.py:50-73`), so a
  missing manifest must mean "unknown", never an error — matching `collect_runs`'s
  skip-don't-raise posture (`repair_stats.py:329-335`, pinned by
  `tests/test_repair_stats.py:470`, `:526`).

## F6 — `resume` overwrites the manifest; `rerun`/`resume` cannot express the flag

`--auto-approve` is declared on **`run` only** (`cli.py:414`). `rerun` (`cli.py:836-843`)
and `resume` (`cli.py:2508-2514`) accept no such flag and fall to `_dispatch_run`'s
default `False` (`cli.py:542`) — verified at `cli.py:2548-2571`. And `resume` re-enters
`_dispatch_run` with the **same run id**, rewriting `runs/<id>/launch.json`
(`cli.py:788-790`).

So `contig run --auto-approve X` followed by `contig resume X` leaves a manifest saying
`false`. That is **self-consistent** — the resume regenerates the `RunRecord` too, so
manifest and record both describe the last invocation — but it is a reasoned property,
not an accident, and deserves a test rather than a footnote.

## F7 — Blast radius on the existing surface

- The string at `cli.py:3787-3788`, *"(a human, or `--auto-approve`, which is never
  recorded)"*, becomes **factually false** and must change.
- Six tests must change deliberately: `tests/test_repair_stats.py:147`, `:174` (whole-dict
  shape), `:305`, `:395`; `tests/test_cli_repair_stats.py:116`, `:142`.
- Two invariants must be **preserved**: missing runs dir → `[]`
  (`tests/test_repair_stats.py:470`); corrupt bundle → skipped, not raised (`:526`).
- `LoadedRun` is `@dataclass(frozen=True)` (`repair_stats.py:180-191`); a new field needs a
  default or all 20+ aggregation tests break at once (`:245-256`).
- `classify_attendance(outcome: str)` takes only a string (`repair_stats.py:163`). A
  run-level fact means either a second argument or moving the decision up to the run level
  — which F2 argues for anyway.

---

## Open questions for the interview

1. **Scope of F1.** Fix `chose_and_retried` → attended in this slice (it is a real bug in
   shipped output), or file it separately? It is independent of persistence.
2. **Scope of F2.** Does run-level attendance derive from the persisted flag (fixing the
   human-approved-index-build over-claim), or stay literal-derived with the flag only
   disambiguating `approved_and_retried`? The first is more correct and more invasive.
3. **F3 confirmation.** `LaunchManifest` as write-only provenance — accepted?
4. **Should `rerun`/`resume` gain `--auto-approve`?** Out of scope by default; the D4
   precedent says a runtime-only knob must be passed per invocation.

## Guardrail check (CLAUDE.md)

Layer 2 — provenance capture + eval instrumentation on the self-heal loop. No Layer 1 (no
NL→workflow), no wet-lab/clinical dependency, no proprietary data. ✓
Honesty posture: push, not demand-pull; no design partner asked; it recovers nothing for a
user and makes the loop's field performance legible. Must be stated as such.
