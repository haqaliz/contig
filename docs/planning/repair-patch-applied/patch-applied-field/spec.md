# Aspect spec — `patch-applied-field`

The blocking aspect. Everything else in this feature consumes what this delivers.

## Problem slice

`RepairStep` records that a patch was *proposed*; nothing records whether it was *enacted*.
This aspect adds the field and makes the engine's eleven recording sites tell the truth.

## In scope

- **R1** `RepairStep.patch_applied: bool = False` (`src/contig/models.py:307-314`), documented
  with the D2 semantics: *"the patch was enacted and the loop proceeded to retry"* — explicitly
  **not** "the run's configuration was mutated", and explicitly **not** "the patch worked".
- **R2** Truthful values at all eleven `_record_attempt` call sites in `src/contig/self_heal.py`,
  derived from control flow (`cont`), never from the outcome string.
- **R4** Back-compat and signature-break tests.

## Out of scope (other aspects)

`verification/reproduce.py` (→ `reproduce-repair-truth`), `heal.py` + frozen scenarios
(→ `heal-guard-truth`), all dashboard and `report.py` work (→ `dashboard-repair-surface`).

## The value table (authoritative — verified in this tree)

| Line | `patch=` | value | why |
|---|---|---|---|
| `:1036` | `None` | `False` | `qc_verdict_flagged` — nothing proposed |
| `:1112` | `None` | `False` | no patch at all |
| `:1126` | `gated` | `False` | budget exhausted **before** apply |
| `:1149` | `gated` | `cont` | `_apply_patch_and_maybe_build` |
| `:1192` | `chosen` | `cont` | `_apply_patch_and_maybe_build` |
| `:1207` | `gated` | `False` | choice refused |
| `:1243` | `gated` | `cont` | `_apply_patch_and_maybe_build` |
| `:1258` | `gated` | `False` | rejected / timed out |
| `:1270` | `safe` | `False` | budget exhausted **before** apply |
| `:1283` | `safe` | `False` | ceiling-blocked **before** apply |
| `:1308` | `safe` | `True` | direct `apply_patch` at `:1293` |

`cont` is already in scope at `:1140`, `:1182`, `:1233`. **No new plumbing, no signature change
on any helper.**

## Acceptance criteria (testable)

1. A rejected patch, an approval timeout, an invalid choice, a budget-exhausted give-up, a
   ceiling give-up, and a failed index build each record `patch_applied=False` **while still
   carrying a non-null `patch`** — the two fields are independent.
2. A resource bump, an approved gated patch, a chosen patch, a built index, a recompressed
   reference, and a `no_progress` **retry** patch each record `True`.
3. `qc_verdict_flagged` records `False`.
4. A pre-change bundle JSON without the key loads and reports `False`.
5. A pre-change signature over a record **with** a non-empty `repair_history` no longer
   verifies; a fresh signature does.
6. A signed record with an **empty** `repair_history` **still verifies** (pins the D5 narrowing).
7. `repair_progress.jsonl` lines carry the field (it flows through `_record_attempt:265-267`).
8. `uv run pytest`, `contig eval-guard`, `contig heal-guard` all green.

## Dependencies and sequencing

None inbound. Blocks all three sibling aspects. Land and commit before they start.

## Risks specific to this aspect

- The `apply_patch`-first trap (`self_heal.py:876-879`) — do not derive from "apply_patch
  returned". Verified: `continue_` is `True` at exactly 4 of 17 returns across
  `_apply_patch_and_maybe_build` / `_build_star_index` / `_recompress_reference`, all
  enacted-and-proceeding.
- The field enters the **signed** canonical payload for both `RunRecord` and `ReproduceRecord`
  (the latter is exercised in the sibling aspect but breaks here, since the model is shared).
