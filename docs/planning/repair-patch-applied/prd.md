# PRD — `repair-patch-applied`: make the repair record say what actually happened

- **Slug:** `repair-patch-applied`
- **Branch:** `feat/repair-patch-applied/aliz`
- **Source:** the follow-up filed by the qc-anomaly slice
  (`docs/planning/qc-anomaly-verdict-trigger/prd.md:352-409`, founder decision 2026-07-28),
  picked by `/contig-next` on 2026-07-29.
- **Capability:** C2/C6 supporting work — the honesty of the self-heal record and the
  structured eval data it carries. Layer 2 throughout.

---

## Problem Statement

`RepairStep` records that a patch was **proposed**. Nothing records whether it was
**applied**. Every consumer therefore has to guess, and they all guess the same wrong way.

The sharpest instance: **a user who rejects a patch at the approval gate is told their run
was `Repaired`.** The engine records `RepairStep(patch=gated, outcome="rejected_by_user")`,
the dashboard's `wasRepaired` (`dashboard/lib/derive.ts:40-42`) reads
`repair_history.some(s => s.patch !== null)`, and the badge fires. The same happens for four
other terminal states that record a non-null patch and return *before* `apply_patch` is ever
called:

| `self_heal.py` | outcome | patch |
|---|---|---|
| `:1126` | `gave_up` (attempt budget exhausted) | `gated` |
| `:1207` | `rejected_by_user` / `invalid_choice_rejected` / `approval_timed_out` | `gated` |
| `:1258` | `rejected_by_user` / `approval_timed_out` | `gated` |
| `:1270` | `gave_up` (attempt budget exhausted) | `safe` |
| `:1283` | `gave_up_at_ceiling` | `safe` |

This is a **correctness over-claim on the differentiator surface**. "No correctness
over-claiming" is a standing guardrail (`FEATURES.md:308`, `CAPABILITY_ROADMAP.md:1825`), and
the visible detect→diagnose→patch→rerun chain is one of the two features the product
positions as the reason to switch (`FEATURES.md:31-38`).

A second, smaller defect rides along: `OUTCOME_META`
(`dashboard/components/run/repair-timeline.tsx:39-76`) maps **3** keys, one of which
(`stopped_for_confirmation`) is emitted **nowhere** in `src/`. Everything else falls through
to `label: outcome` in `OUTCOME_META.gave_up.className` (`:79-83`), so `rejected_by_user`
renders as the raw string `rejected_by_user` **dressed in give-up styling** — a user who
rejected a fix sees something that reads like the engine failed.

**Evidence it is real:** found by the qc-anomaly slice's own Phase-3.5 review, reproduced by
reading the code in this tree, and already half-acknowledged in the repo — the header comment
of `dashboard/e2e/repair-truthfulness.spec.ts:11` asserts *"The badge now means what it says:
a patch was applied"*, which is **not true today**.

**Honest limit, stated up front:** this is **push, not demand-pull**. No design partner asked
for it; Contig is pre-revenue and no user has reported it. The driver is a self-audit. Nothing
in this PRD claims otherwise.

---

## Goals & Success Metrics

| Goal | Measure |
|---|---|
| No surface claims a repair that did not happen | A rejected/timed-out/budget-exhausted/ceiling-blocked/build-failed step never renders as `Repaired`, asserted in both pytest and Playwright |
| Every live outcome literal renders as intended prose | 0 outcomes fall through `OUTCOME_META`'s raw-literal fallback; the dead key is gone |
| The signal is durable, not a hand-maintained list | `patch_applied` is derived from control flow (`continue_`), so a future outcome literal is correct without touching a map |
| The disclosed `recovery_rate` artifact is retired | `heal-guard`'s `recovery_rate` stops counting a green-by-construction scenario as recovered |
| No guarded number regresses | `heal-guard` `outcome_match_rate` stays **1.0**; `eval-guard` stays **0.923**, both untouched-by-design |

**Read these honestly: they are conformance assertions, not outcome metrics.** Every row above
is something a test can check about our own code. None of them measures whether a *user*
trusted the product more, because there are no users yet to measure. The only numbers that
move are internal (`recovery_rate` 0.667 → 0.556), and that movement is a **correction**, not
an improvement. There is no falsifiable claim of user benefit in this slice, and none should
be manufactured.

**Non-metric:** this ships no new recovery capability. It recovers nothing it did not recover
before. Calling it a self-heal improvement would be false.

**Effort and sequencing.** Small-to-medium; four aspects with one hard ordering constraint —
the field (A1) must land before the three consumers (A2/A3/A4), which are then mutually
independent and can run in parallel.

| Aspect | Boundary | Depends on |
|---|---|---|
| `patch-applied-field` | `models.py` + the 11 `self_heal.py` sites + back-compat/signature tests (R1, R2, R4) | — |
| `reproduce-repair-truth` | `verification/reproduce.py`'s 3 steps (R3) | A1 |
| `heal-guard-truth` | `expected_patch_applied`, the `recovered` redefinition, the deliberate baseline refreeze (R7, R8) | A1 |
| `dashboard-repair-surface` | `types.ts`, `derive.ts`, `OUTCOME_META`, fixtures + e2e (R5, R6, R9) | A1 |

The A3 baseline refreeze must be its **own commit** with the redefinition stated in the
message, so the change to a recorded metric is reviewable in isolation rather than buried in a
feature diff.

---

## Users & Scenarios

**These scenarios are constructed, not observed.** Contig is pre-revenue with no design
partners on this surface, so nothing below is validated user need — it is a reading of who
*would* hit the defect. Treated as evidence it would be over-claiming.

- **Persona A (lone computational biologist)** rejects a `needs_confirmation` patch at the
  approval gate because they want to inspect the reference themselves. Today the run list
  badges that run `Repaired` and the timeline shows `rejected_by_user` in give-up grey. After:
  no badge, and a clear "you rejected this fix" outcome.
- **Persona C/D (core facility, biotech)** hand a signed bundle to a colleague as evidence of
  what the engine did. Today `repair_history` cannot distinguish "we tried and you said no"
  from "we fixed it". After: one boolean, inside the signed payload.
- **Us (moat #2)** — the cross-run "Repair success-rate analytics" item (`FEATURES.md:217`) is
  unbuildable while proposed and applied are indistinguishable. This slice supplies the field,
  not the view.

---

## Decisions taken (interview, 2026-07-29)

**D1 — Structured signed field, not a derived mapping.**
The dig established that `outcome` alone **already determines** applied-vs-not today: all 18
live literals partition cleanly. A derived `outcome → applied` map was therefore a viable,
signature-break-free alternative and was **considered and rejected**. Reason: the map is
hand-maintained, and a literal added later silently defaults to "not applied" — reintroducing
exactly this bug by a different door. `patch_applied` is derived from **control flow**, so a
new literal recorded at an existing site is correct with no map to update.
*Cost accepted: a signature break (see D5).*

**D2 — Semantics: "the patch was enacted and the loop proceeded to retry."**
Not "the run's configuration was mutated". `apply_patch` is a documented **no-op** for
`code`/`retry` patches (`self_heal.py:549`, "The re-run itself is the fix"), and the
`no_progress` heal is exactly that shape — under a "mutated" reading a successful
`no_progress` heal would report **no patch applied**, a new under-claim. The chosen meaning
also matches reproduce's `retry_failed` (the install *succeeded*; the retry then failed):
**applied ≠ successful.** This meaning MUST be documented on the field itself, because the
name `patch_applied` invites the narrower reading.

**D3 — Legacy default `False`, plain `bool`.**
A pre-change bundle reports "no patch applied". This retro-labels old bundles that genuinely
did patch — an **under-claim**, which is the safe direction of error for a feature whose whole
purpose is to stop over-claiming. A tri-state `bool | None` was considered and rejected: it
forces three branches on every consumer and an "unknown" rendering, and the repo's `source_*`
precedent used `None` because **`None` was a real value** (a local run), not because it meant
unknown.

**D4 — `heal.py`'s `recovered` IS redefined** (founder decision, overriding the dig's
recommendation and the qc-anomaly slice's earlier deferral). See "The `recovered`
redefinition" below for exactly what it costs and why it is safe.

**D5 — The signature break is narrower than its predecessors, and will be described as such.**
`RepairStep` is nested inside a list, so a record with an **empty `repair_history` serializes
byte-identically** and its old signature still verifies. The blast radius is "signed bundles
that recorded at least one repair attempt" — not "every signed bundle", which is what C8 slice
6 was. Over-claiming the breakage would be its own small dishonesty.

---

## Requirements

### Must-have

**R1 — `RepairStep.patch_applied: bool = False`** on the model (`models.py:307-314`), with a
docstring stating the D2 semantics verbatim.

**R2 — Truthful wiring at all eleven `_record_attempt` sites** in `self_heal.py`. Derived from
control flow, never from the outcome string:

| Line | patch | value | source |
|---|---|---|---|
| `:1036` | `None` | `False` | qc_verdict_flagged — nothing proposed |
| `:1112` | `None` | `False` | no patch at all |
| `:1126` | `gated` | `False` | budget exhausted before apply |
| `:1149` | `gated` | `cont` | `_apply_patch_and_maybe_build` |
| `:1192` | `chosen` | `cont` | `_apply_patch_and_maybe_build` |
| `:1207` | `gated` | `False` | choice refused |
| `:1243` | `gated` | `cont` | `_apply_patch_and_maybe_build` |
| `:1258` | `gated` | `False` | rejected / timed out |
| `:1270` | `safe` | `False` | budget exhausted before apply |
| `:1283` | `safe` | `False` | ceiling-blocked before apply |
| `:1308` | `safe` | `True` | direct `apply_patch` at `:1293` |

`cont` is already destructured into scope at `:1140`, `:1182`, `:1233` — **no new plumbing**.

> ⚠️ **Do NOT set the flag "wherever `apply_patch` returns."** It is called on the *first
> line* of `_apply_patch_and_maybe_build` (`:879`), before the build/recompress is attempted —
> the code says so at `:876`. That rule would stamp `index_build_failed`,
> `index_unresolvable`, `reference_recompress_failed` and `reference_recompress_unresolvable`
> as applied, hardening this exact bug into the **signed** record.

**R3 — Wire `verification/reproduce.py`'s three steps** (`:1236-1268`), which share the same
`RepairStep` type via `ReproduceRecord.repair_history` (`models.py:684`) and render as
`env-repair:` lines (`report.py:95-97`). Truth is `install_rc == 0`:
`install_failed` → `False`; `retry_failed` → **`True`**; `installed_and_retried` → `True`.
*Skipping this would let three steps silently take the default — a NEW dishonesty in the very
surface this slice fixes.*

**R4 — Back-compat + signature break, both pinned by test.** A pre-change bundle still
**loads** (field defaults). A pre-change **signed** record with a non-empty `repair_history`
no longer **verifies**, and a fresh signature does — mirroring
`tests/test_reproduce_checkout_hash.py:354-381`. Additionally pin the D5 narrowing: a signed
record with an **empty** `repair_history` **still verifies**.

**R5 — `wasRepaired` reads the field.** `dashboard/lib/derive.ts:40-42` becomes
`record.repair_history.some((s) => s.patch_applied)`. The TS `RepairStep`
(`dashboard/lib/types.ts:70-75`) and `RepairStepLite` (`:360`) gain the field — note both are
**hand-maintained** and `RepairStep` already omits `detail`, a pre-existing drift.

**R6 — Complete `OUTCOME_META`.** Map every live literal, delete the dead
`stopped_for_confirmation` key, and keep the fallback (defensive, but no longer reachable by a
known literal). Rejection/timeout outcomes must be visually distinct from `gave_up` — the
engine did not fail, the human declined.

**R7 — `heal_scenarios.jsonl` gains `expected_patch_applied`** on an optional `HealScenario`
field, so the flag is guarded through the **real** loop in CI rather than only by unit tests.
Precedent: the qc-anomaly slice added an optional `HealScenario` field the same way. Requires
a deliberate `heal-guard --update-baseline` refreeze.

**R8 — Redefine `heal.py`'s `recovered`** (D4). See below.

**R9 — Correct the false comment** at `dashboard/e2e/repair-truthfulness.spec.ts:11`, which
already claims the property this slice is only now delivering.

### Should-have

**R10** — `repair_progress.jsonl` (written by `_record_attempt` at `:265-267`) carries the
field automatically; assert it, since the live self-heal feed reads it.
**R11** — the text/HTML report (`report.py:153-160`, `:334-340`) renders repair steps without
distinguishing applied; surface the distinction there too.

### Out of scope

- Type-constraining `RepairStep.outcome` to a `Literal` (18 values, two modules, its own
  back-compat question).
- Building the cross-run repair success-rate analytics view (`FEATURES.md:217`).
- Adding patch/repair data to `FailureCase`/the corpus (`corpus.py` carries none today).
- Any new repair strategy, failure class, QC check, band, or calibration.
- Any exit-code change. Any Layer-1 surface.

---

## The `recovered` redefinition (D4) — what it costs, precisely

`heal.py:153` computes `recovered = RunSummary.from_events(record.events).succeeded`. It is
**event-derived**, which is why the qc-anomaly scenario — green from attempt 1 — computes
`recovered=True` although nothing was recovered. The qc-anomaly slice **disclosed this as an
artifact** rather than fixing it:

> "The `recovery_rate` move **0.625 → 0.667 is an artifact**, not an improvement … disclosed
> rather than fixed" (`CAPABILITY_ROADMAP.md:1128-1132`)

`patch_applied` makes the honest definition available for the first time:
`recovered = succeeded AND any(step.patch_applied)`. **So this requirement retires a defect
the repo already admitted to.**

**Impact on the 9 frozen scenarios — exactly one changes:**

| Scenario | now | after |
|---|---|---|
| `oom-heal`, `time-limit-heal`, `missing-index-buildable-heal`, `approval-approved-heal`, `no-progress-heal` | True | True |
| `missing-index-unresolvable-giveup`, `tool-crash-giveup`, `approval-timeout-giveup` | False | False |
| **`qc-anomaly-verdict-flagged`** | **True** | **False** |

**The guarded number does not move.** `recovered` feeds `divergence` → `matched` →
`outcome_match_rate` (`heal.py:168-171`), so `outcome_match_rate` stays **1.0** *provided*
`expected_recovered` is corrected to `false` for that one scenario in the frozen file. That
correction is the point, not a workaround.

`recovery_rate` (informational-only, never guarded) moves **0.667 → 0.556** (6/9 → 5/9).

**The honest cost, which must be recorded in the CHANGELOG and not softened:** `recovery_rate`
has five recorded trend points in `heal_history.jsonl` (0.571 ×3, 0.625, 0.667), all computed
under the **old** definition. The sixth point is **not comparable** to them. That
non-comparability is the exact objection the qc-anomaly slice raised when it declined this
change; it is accepted here deliberately, because the metric is informational-only and the new
definition is truthful where the old one was not.

---

## Technical Considerations

- **Architecture fit:** one field on one model, set at eleven existing call sites from a
  boolean already in scope, plus three sites in the reproduce loop. No new module, seam,
  dependency, CLI flag, or `FailureClass`.
- **Reproducibility/verification impact:** the field enters the **signed** canonical payload
  (`signing.py:63`, `record.model_dump(mode="json")`), for both `RunRecord` and
  `ReproduceRecord`. This is the fourth disclosed signature break, and the narrowest (D5).
- **Blast radius:** `models.py`, `self_heal.py`, `verification/reproduce.py`, `heal.py`,
  `heal_scenarios.jsonl` + `heal_baseline.json`, `report.py`, `dashboard/lib/types.ts`,
  `dashboard/lib/derive.ts`, `dashboard/components/run/repair-timeline.tsx`,
  `dashboard/e2e/` fixtures + specs.
- **`eval-guard` is untouched.** The detector corpus and holdout baseline contain no
  `RepairStep`; held-out accuracy stays 0.923 and any claim it improved would be false.
- **Test discipline:** test-first (RED → GREEN → REFACTOR). CI runs `uv run pytest`,
  `contig eval-guard`, `contig heal-guard`, then `tsc --noEmit`, `npm run lint`,
  `npx playwright test`.

---

## Risks & Open Questions

| # | Risk | Mitigation |
|---|---|---|
| RISK-1 | The signature break annoys a signing user | Bounded to opt-in `CONTIG_SIGNING_KEY` **and** to bundles with a non-empty `repair_history`; pinned by test; disclosed in CHANGELOG as the 4th and narrowest |
| RISK-2 | `patch_applied` is read as "config mutated" and becomes a second untrustworthy signal | D2 documented **on the field**; a test pins that a `retry`-kind patch records `True` |
| RISK-3 | ~~A hidden path where `cont` is True but the patch was not enacted~~ — **VERIFIED CLEAN, see below** | Still pin each return with a test, but this is now confirmation, not discovery |
| RISK-4 | `recovery_rate` trend silently misread across the redefinition | Recorded explicitly in the CHANGELOG and in `heal_baseline.json`'s refreeze note |
| RISK-5 | Dashboard fixtures are hand-written JSON; a fixture that omits the field passes vacuously | Add the field explicitly to fixtures, and add a **new** fixture for the sharp case (a rejected patch) so the assertion is positive, not merely absent |
| RISK-6 | Push, not demand-pull; no user asked | Stated as an honest limit, not softened |

### RISK-3 — verified clean (all 17 returns enumerated)

`continue_` is a **sound** proxy for "enacted". Every return across the three helpers was read:

- `_apply_patch_and_maybe_build` (`:838-937`) — `True` at `:883` (non-build, non-recompress:
  `apply_patch` did the work, `default_outcome` = `patched_/approved_/chose_and_retried`) and
  `:937` (`built_index_and_retried`). `False` at `:886`, `:907`, `:921`, `:930`
  (`index_unresolvable` ×2, `index_build_failed` ×2). Two returns delegate.
- `_build_star_index` (`:590-697`) — `True` only at `:697`
  (`built_index_and_retried`); `False` at `:627`, `:636`, `:644`, `:675`, `:683`.
- `_recompress_reference` (`:754-835`) — `True` only at `:835`
  (`recompressed_reference_and_retried`); `False` at `:785`, `:794`, `:804`, `:826`.

**4 `True` returns, all enacted-and-proceeding; 13 `False` returns, all honest give-ups where
nothing was enacted. No inconsistency exists in either direction.** (An exception raised by
`index_builder` propagates rather than returning, so no `RepairStep` is recorded at all — not
a false-positive path.)

### `heal_scenarios.jsonl` refreeze cost — verified

`corpus_sha = sha256_file(scenarios_path)` (`cli.py:2725`) hashes the **file bytes**. Therefore:
adding the optional field to the `HealScenario` **model** alone changes nothing; editing the
**jsonl** (R7's `expected_patch_applied`, and R8's one corrected `expected_recovered`) changes
the sha and triggers the loud mismatch warning. **Both requirements are covered by one
deliberate `--update-baseline` refreeze** — which confirms grouping them into a single aspect
(A3) with its own commit.

**Q-A — RESOLVED by D2, recorded so it is not re-opened as a bug.** The suspect case: a
`resource` patch fully absorbed by the never-shrink/ceiling clamp (`apply_patch:564-573`)
produces an **identical** target, yet records `patched_and_retried` with `patch_applied=True`.
Under D2's semantics — *enacted and the loop proceeded* — **`True` is correct**: the patch was
carried out, and the fact that the clamp left the value unchanged is a property of the clamp,
not of whether the patch ran. This is exactly why D2 was chosen over "config was mutated",
which would have made this case ambiguous and required a carve-out. (`_resource_ceiling_block`
at `:1281` already catches the *already-at-ceiling* case before apply, recording
`gave_up_at_ceiling` → `False`.) What remains is verification, not a design question: pin
every `return` in the two helpers with a test (RISK-3).

**Q-B (open):** does `report.py` (R11) get the distinction in this slice or a follow-on? It is
should-have, so it yields first if the slice grows.

**Q-C (open, answer before starting):** what future outcome literal do we actually expect to
be added at an existing recording site? D1 bought durability against that possibility and paid
a real signature break for it. If the honest answer is "none foreseeable", D1 is still
defensible — control-flow derivation is correct *by construction* rather than by review — but
we should say that is the reason, rather than implying a concrete pending literal.

---

## Acceptance (test-first)

1. Each of the eleven self-heal sites records the value in the R2 table — a rejected patch,
   an approval timeout, a budget-exhausted give-up, a ceiling give-up, and a failed index
   build all record `patch_applied=False` **while still carrying a non-null patch**.
2. A successful resource bump, an approved gated patch, a chosen patch, a built index, a
   recompressed reference, and a `no_progress` retry all record `True`.
3. Reproduce: `install_failed` → `False`; `retry_failed` → `True`; `installed_and_retried` →
   `True`.
4. A pre-change bundle JSON (no field) loads, and reports `False`.
5. A pre-change signature over a record **with** repair history no longer verifies; a fresh
   one does; a signed record with an **empty** repair history **still verifies**.
6. `heal-guard`: `outcome_match_rate` stays 1.0 over 9 scenarios with the corrected
   `expected_recovered`; `recovery_rate` reports 0.556.
7. Playwright: a run whose only patch was **rejected** shows no `Repaired` badge and renders a
   distinct, non-give-up, non-snake_case outcome label; the existing applied-patch positive
   control still shows `Repaired`.
8. `uv run pytest`, `contig eval-guard`, `contig heal-guard`, `tsc --noEmit`, `npm run lint`,
   `npx playwright test` all green.
