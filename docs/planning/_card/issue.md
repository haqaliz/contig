# Card: feat / repair-patch-applied

- **Type:** feat
- **Id/slug:** `repair-patch-applied`
- **Owner:** aliz
- **Branch:** `feat/repair-patch-applied/aliz`
- **Source:** inline brief (no GitHub issue — `gh issue list` returns "No Issues") — carried
  from the `/contig-next` recommendation (2026-07-29), the next slice after the
  `qc_anomaly` verdict trigger merged.

## Brief

Add `RepairStep.patch_applied` and drive the dashboard's repair badge off it, so the
self-heal surface stops claiming "Repaired" for a patch that was only **proposed** — most
sharply, a user who *rejected* a patch at the approval gate is currently told their run was
`Repaired`.

The design is already filed in `docs/planning/qc-anomaly-verdict-trigger/prd.md:352-409`
("Filed follow-up — `wasRepaired` still overclaims, and `OUTCOME_META` is thirteen short",
founder decision 2026-07-28):

- Derive the flag from `_apply_patch_and_maybe_build`'s returned `continue_` boolean
  (`self_heal.py:849`) plus the `:1266` site — **NOT** from "wherever `apply_patch` returns".
  That naive rule would stamp `index_build_failed` / `index_unresolvable` /
  `reference_recompress_failed` / `reference_recompress_unresolvable` as applied, hardening
  the very bug into the **signed** record, where it is far more expensive to correct than a
  dashboard predicate.
- Also map the unmapped outcome literals: `RepairStep.outcome` is a bare `str`
  (`models.py:313`) with **15** live values, and the dashboard's `OUTCOME_META` maps 2 real
  ones (one of its 3 keys, `stopped_for_confirmation`, appears nowhere in `src/` — it is
  dead), so `rejected_by_user` / `approval_timed_out` / `gave_up_at_ceiling` and ten others
  render today as mangled snake_case dressed in give-up styling.

## Why (moat + shipped state)

- **It is the explicitly filed follow-on of the slice that just merged.** Commit `965e42b`
  ("fix(dashboard): a repair badge means a patch, not a recorded step") moved `wasRepaired`
  from `repair_history.length > 0` to `some(s => s.patch !== null)` — strictly better, but
  that means *proposed*, not *applied*. Five paths record a non-null patch and return before
  `apply_patch` ever runs (`self_heal.py:1102, :1183, :1234, :1246, :1257`).
- **It is an over-claim on the differentiator surface.** "No correctness over-claiming" is a
  standing guardrail (`FEATURES.md:308`, `CAPABILITY_ROADMAP.md:1825`), and the self-heal
  chain is one of the two headline differentiators (`FEATURES.md:108-115`).
- **It is corpus/eval work, not cosmetics.** No structured field distinguishes proposed from
  applied today, which is what `heal-guard`'s informational `recovery_rate` and the still
  unbuilt "Repair success-rate analytics" (`FEATURES.md:217`) both need — moat #2 fuel
  (`CLAUDE.md` constraint #2).
- **It is unblocked**, unlike the neighbouring C6/C7 item (folding C1/C3 signals into one
  eval number is **blocked on a labeling design** — `CAPABILITY_ROADMAP.md:1029-1030`,
  restated as out of scope at `qc-anomaly-verdict-trigger/prd.md:346`).

## KNOWN CAVEATS (confront in the dig, do not discover late)

1. **This touches the signed `RunRecord`.** `canonical_record_bytes` is
   `record.model_dump(mode="json")` (`signing.py:63`) and includes every field, so adding
   `RepairStep.patch_applied` is the **fourth disclosed signature break** — after C8 slice 6
   (`source_url`/`source_commit`), C8 slice 8 (`source_tree_sha256`), and the somatic
   FAIL-floor `verdict` field. Pre-change signed bundles must still **load**, and the fact
   that they no longer **verify** must be pinned by a test, the way the prior three were. The
   filed follow-up says this is *precisely why it is its own slice*.
2. **The legacy default is a real design decision, not a formality.** A plain
   `bool = False` makes every pre-change bundle claim *no patch applied*, which under-claims
   where the old record genuinely did apply one. A tri-state (`bool | None = None`, `None` =
   unknown, rendered as today) may be the honest default. Decide deliberately; do not default
   by habit.
3. **Do NOT set the flag "wherever `apply_patch` returns."** `_apply_patch_and_maybe_build`
   calls `apply_patch` on its **first line** (`self_heal.py:879`), before it knows whether the
   build or recompress succeeded — the code says so itself at `:876` ("The build IS the fix
   (apply_patch is a no-op for build_index)"). Use the `continue_` boolean, the last element
   of its documented 5-tuple return (`-> tuple[..., bool]`, `:849`), which is `True` exactly
   for the applied-and-proceeding cases and `False` for all four failure branches.

## The five over-claiming sites (from the filed follow-up)

| Site | Outcome | Patch |
|---|---|---|
| `self_heal.py:1102` | `gave_up` (attempt budget exhausted) | `gated` |
| `self_heal.py:1183` | `rejected_by_user` / `invalid_choice_rejected` / `approval_timed_out` | `gated` |
| `self_heal.py:1234` | `rejected_by_user` / `approval_timed_out` | `gated` |
| `self_heal.py:1246` | `gave_up` (attempt budget exhausted) | `safe` |
| `self_heal.py:1257` | `gave_up_at_ceiling` | `safe` |

## The 15 live `RepairStep.outcome` literals (untyped `str` today)

`patched_and_retried`, `approved_and_retried`, `chose_and_retried`,
`built_index_and_retried`, `recompressed_reference_and_retried`, `gave_up`,
`gave_up_at_ceiling`, `rejected_by_user`, `approval_timed_out`, `invalid_choice_rejected`,
`index_build_failed`, `index_unresolvable`, `reference_recompress_failed`,
`reference_recompress_unresolvable`, `qc_verdict_flagged`.

## Shipped precedents to mirror

- **`docs/planning/qc-anomaly-verdict-trigger/`** — the slice that filed this follow-up;
  its Phase 0 established the signature-safety approach this slice must re-verify, and its
  `965e42b` dashboard fix is what this builds on.
- **`docs/planning/reproduce-remote-intake/`** (slice 6) and
  **`docs/planning/reproduce-checkout-hash/`** (slice 8) — the two prior signed-field
  additions, including how each pinned the break with a
  `test_pre_slice_N_signature_...no_longer_verifies` test.
- **`docs/planning/somatic-empty-callset-fail/`** — the `verdict`-field signature-break
  disclosure and its blast-radius framing.

## Deferred (name in the PRD, out of scope unless the dig argues otherwise)

- Type-constraining `RepairStep.outcome` into a `Literal` (a separate, wider change).
- Cross-run "repair success-rate analytics" aggregation (`FEATURES.md:217`) — this slice
  supplies the field it needs, not the view.
- Folding C1/C3 corroboration signals into one eval number (blocked on a labeling design).
- Any new repair strategy, failure class, band, or QC check.
- Any Layer-1 (NL → workflow) surface.
