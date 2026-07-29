# Phase 2 — Understanding: `repair-patch-applied`

Written after reading the code first-hand in the worktree (`origin/master`, post-`cc91155`).
Every line reference below was verified in this tree, **not** taken from the filed follow-up.

---

## 1. What the work is really asking

Add one structured boolean to `RepairStep` that answers: **was this patch actually carried
out?** — and then drive the surfaces off it instead of off `patch !== null`.

The distinction that makes it non-trivial: **proposed ≠ applied ≠ successful.** Three
different things, currently collapsed into one.

---

## 2. Verified ground truth: the eleven `_record_attempt` sites

`_record_attempt` (`self_heal.py:253-267`) is the single funnel — it appends to
`repair_history` **and** writes a line to `repair_progress.jsonl` (the live self-heal feed).
So the new field lands on the live surface for free, and must be honest there too.

| Line | `patch=` | outcome | patch actually applied? |
|---|---|---|---|
| 1036 | `None` | `qc_verdict_flagged` | **No** |
| 1112 | `None` | `gave_up` | **No** |
| 1126 | `gated` | `gave_up` (budget exhausted) | **No** |
| 1149 | `gated` | from `_apply_patch_and_maybe_build` | **= `cont`** |
| 1192 | `chosen` | from `_apply_patch_and_maybe_build` | **= `cont`** |
| 1207 | `gated` | `rejected_by_user` / `invalid_choice_rejected` / `approval_timed_out` | **No** |
| 1243 | `gated` | from `_apply_patch_and_maybe_build` | **= `cont`** |
| 1258 | `gated` | `rejected_by_user` / `approval_timed_out` | **No** |
| 1270 | `safe` | `gave_up` (budget exhausted) | **No** |
| 1283 | `safe` | `gave_up_at_ceiling` | **No** |
| 1308 | `safe` | `patched_and_retried` | **Yes** (direct `apply_patch` at `:1293`) |

**The filed follow-up's design is confirmed correct.** `cont` (the 5th element of
`_apply_patch_and_maybe_build`'s documented return, `:849`/`:853`) is destructured into scope
at all three sites (`:1140`, `:1182`, `:1233`) *before* the `_record_attempt` call that
follows, so the field can be set with no new plumbing at all. The only direct `apply_patch`
call in the loop is `:1293`, feeding `:1308`.

Its warning is also confirmed: `apply_patch` is called on the **first line** of
`_apply_patch_and_maybe_build` (`:879`), before the build/recompress is even attempted, with
the code saying so at `:876` ("The build IS the fix (apply_patch is a no-op for
build_index)"). A naive "set it wherever `apply_patch` returns" rule would stamp
`index_build_failed`, `index_unresolvable`, `reference_recompress_failed` and
`reference_recompress_unresolvable` as applied.

**Line numbers in the filed follow-up have drifted.** It cites
`:1102/:1183/:1234/:1246/:1257`; the *set* of sites is right, but the numbers are ~+20 off in
this tree. `:879` and `:849` still hold. Use the table above, not the PRD's numbers.

---

## 3. THREE FINDINGS THAT CORRECT THE BRIEF

### 3.1 There are 18 live outcome literals, not 15

The follow-up's list is `self_heal.py`-only. `verification/reproduce.py:1236-1268` constructs
three more `RepairStep`s with their own literals, none of which appear anywhere else in `src/`
or in the dashboard:

- `install_failed` (`:1240`) — pip install failed → **not applied**
- `retry_failed` (`:1255`) — install **succeeded**, retry still failed → **applied**
- `installed_and_retried` (`:1265`) → **applied**

`retry_failed` is the sharpest available proof that **applied ≠ successful**, and it is a
strong argument for the field's semantics and its name.

### 3.2 `ReproduceRecord.repair_history` is the same `RepairStep` type

`models.py:336` (RunRecord) and `models.py:684` (ReproduceRecord) share it. So the field
lands in the **reproduce** bundle as well, and if this slice only wires `self_heal.py`, the
three reproduce steps silently take the default — manufacturing a *new* dishonesty in exactly
the surface (`report.py:95-97` renders `env-repair: {outcome}`) the slice claims to fix.
**Scope decision required in the PRD:** either wire reproduce too (cheap and mechanical — the
truth is `install_rc == 0`), or explicitly justify leaving it unknown there.

### 3.3 The signature break is materially narrower than slices 6 and 8

`RepairStep` is **nested inside a list**. A record with an empty `repair_history` serializes
byte-identically before and after, so its old signature **still verifies**. The blast radius
is "signed bundles that recorded at least one repair attempt", not "every signed bundle" —
unlike C8 slice 6, which broke *every* signed reproduce bundle. Worth stating precisely
rather than inheriting the brief's framing; over-claiming the breakage is its own small
dishonesty. The break is still real and must be pinned by a test, mirroring
`tests/test_reproduce_checkout_hash.py:354-381` (build the pre-change canonical bytes by
stripping the new key, sign those, assert `verify_signature(...) is False`, then assert a
fresh signature *does* verify).

---

## 4. The open questions the PRD must settle

**Q1 — What does the field actually mean?** `apply_patch` is documented (`self_heal.py:549`)
as changing **nothing** for `code`/`retry` patches: "The re-run itself is the fix." The
`no_progress` heal is exactly such a patch (`kind="retry"`, `risk="safe"`). So for it, `cont`
is True and nothing was mutated. Two honest readings:

- **(a)** "the patch's operation was carried out and the loop proceeded" → retry patches are
  `True`. Matches `cont`. Matches `retry_failed` being `True`.
- **(b)** "the run's configuration was mutated" → retry patches are `False`.

A bare name like `patch_applied` invites (b) while the implementation gives (a). Either
settle on (a) and document it on the field, or pick a name that says (a) out loud.

**Q2 — Legacy default: `False` or tri-state `None`?** A plain `bool = False` retro-labels
every pre-change bundle "no patch applied", which is wrong for the ones that did patch. A
`bool | None = None` ("unknown, pre-field record") is honest but forces every consumer to
handle three states, and the dashboard needs an explicit unknown rendering. Note the repo's
own precedent cuts the other way: `source_url` / `source_commit` / `source_tree_sha256` all
defaulted to `None` because **`None` was a real value** (a local run), not because it meant
"unknown".

**Q3 — Does completing `OUTCOME_META` belong in this slice or its own?** They are separable:
the badge fix needs the new field; the label map is pure presentation. Bundling is defensible
(same over-claim, filed together) but the blast radii differ — one touches the signed record,
one touches a `.tsx` map.

**Q4 — Should `heal_scenarios.jsonl` gain `expected_patch_applied`?** That would guard the
new field through the **real** loop in CI rather than only via unit tests, with direct
precedent (the qc-anomaly slice added an optional `HealScenario` field and refroze
deliberately). Cost: it changes `heal_scenarios.jsonl` bytes → changes `corpus_sha` →
requires a deliberate `--update-baseline` refreeze.

---

## 5. Explicitly NOT this slice (verified reasons, not guesses)

- **Redefining `heal.py`'s `recovered`.** It is
  `RunSummary.from_events(record.events).succeeded` (`heal.py:153`) — event-derived, which is
  why the green-by-construction qc-anomaly scenario computes `recovered=True` though nothing
  was recovered. `patch_applied` would make it truthful, **but** `recovered` is not merely
  informational: a mismatch against `expected_recovered` enters `divergence`
  (`heal.py:168-171`) and therefore `matched`, i.e. the **guarded** `outcome_match_rate`.
  Changing it would move a guarded number and retroactively change the meaning of every
  recorded `heal_history` point. The docs already declined this.
- **Type-constraining `RepairStep.outcome` to a `Literal`** — 18 values across two modules;
  a wider change with its own back-compat question (an old bundle carrying a retired literal
  must still load).
- **Cross-run repair success-rate analytics** (`FEATURES.md:217`) — this slice supplies the
  field that view needs; it does not build the view.
- **`FailureCase`/corpus capture of patch info** — `corpus.py` carries no patch/repair fields
  at all today. Adding them is a separate corpus-schema decision.

---

## 6. Strategic check (CLAUDE.md)

Layer 2, squarely: it hardens the honesty of the self-heal/verify record and adds structured
evaluation data to the signed bundle. No Layer-1 surface, no new dependency, no wet-lab or
clinical dependency. It is **push, not demand-pull** — no design partner asked; the driver is
a self-audit finding. State that as an honest limit rather than dressing it up.

---

## 7. Test surfaces to extend, not duplicate

- `tests/test_self_heal.py` (114 KB) — the main loop's unit tests.
- `tests/test_heal_scenarios.py` / `tests/test_heal_guard.py` — the frozen-scenario harness.
- `tests/test_models.py`, `tests/test_signing.py` — model + signature contracts.
- `tests/test_reproduce.py` (97 KB) — the reproduce loop's `repair_history`.
- `tests/test_report.py` — text/HTML rendering of repair history (`report.py:153-160`,
  `:334-340`).
- `dashboard/e2e/repair-truthfulness.spec.ts` — **the** file for this slice. Its header
  comment already claims *"The badge now means what it says: a patch was applied"*, which is
  precisely the statement that is **not yet true**; correcting it is part of the work.
- CI runs `uv run pytest`, `contig eval-guard`, `contig heal-guard`, then `tsc --noEmit`,
  `npm run lint`, `npx playwright test` (`.github/workflows/ci.yml`).
