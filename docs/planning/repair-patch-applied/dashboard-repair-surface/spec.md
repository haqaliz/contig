# Aspect spec — `dashboard-repair-surface`

The user-visible half. This is where the over-claim is actually seen.

## Problem slice

1. `wasRepaired` (`dashboard/lib/derive.ts:40-42`) is
   `record.repair_history.some((s) => s.patch !== null)` — i.e. **proposed**, not applied. A
   user who rejected a patch is badged `Repaired`.
2. `OUTCOME_META` (`dashboard/components/run/repair-timeline.tsx:39-76`) maps **3** keys, one
   of which (`stopped_for_confirmation`) is emitted **nowhere** in `src/` and is dead. Every
   unmapped literal falls through `:79-83` to `label: outcome` in
   `OUTCOME_META.gave_up.className` — so `rejected_by_user` renders as raw snake_case **in
   give-up styling**. A user who declined a fix sees something that reads like the engine failed.

## In scope

- **R5** — `wasRepaired` reads `patch_applied`. Add the field to the hand-maintained TS types:
  `RepairStep` (`dashboard/lib/types.ts:70-75`) and `RepairStepLite` (`:360`, the
  `repair_progress.jsonl` live-feed shape). *Note a pre-existing drift: the TS `RepairStep`
  omits `detail`, which the Python model has. Do not fix that here; note it.*
- **R6** — map every live outcome literal in `OUTCOME_META`; delete the dead
  `stopped_for_confirmation` key. Rejection/timeout outcomes must be **visually distinct from
  `gave_up`** — the engine did not fail, the human declined. Keep the fallback as a defensive
  path, but no known literal should reach it.
- **R9** — correct the false claim at `dashboard/e2e/repair-truthfulness.spec.ts:11` ("The
  badge now means what it says: a patch was applied"), which only becomes true with this work.
- **R11 (should-have)** — surface the applied/not-applied distinction in `src/contig/report.py`
  (`:153-160` text, `:334-340` HTML). **Yields first if the aspect grows.**

## The literals to map

From `self_heal.py` (15): `patched_and_retried`, `approved_and_retried`, `chose_and_retried`,
`built_index_and_retried`, `recompressed_reference_and_retried`, `gave_up`,
`gave_up_at_ceiling`, `rejected_by_user`, `approval_timed_out`, `invalid_choice_rejected`,
`index_build_failed`, `index_unresolvable`, `reference_recompress_failed`,
`reference_recompress_unresolvable`, `qc_verdict_flagged`.
From `verification/reproduce.py` (3): `install_failed`, `retry_failed`,
`installed_and_retried`.

Group them into three visual families: **applied** (the `*_and_retried` set), **the human
declined** (`rejected_by_user`, `approval_timed_out`, `invalid_choice_rejected`), and **the
engine gave up honestly** (everything else). `retry_failed` belongs with *applied* — the
install ran; the retry then failed — and its label should say so.

## Acceptance criteria (testable, Playwright)

1. A run whose only patch was **rejected** shows **no** `Repaired` badge in the runs table.
   *A new fixture is required for this — it is the sharp case and none exists today.*
2. That run's timeline shows a human-declined label (not raw `rejected_by_user`) whose class
   **differs** from `gave_up`'s — asserted as a negative class comparison, matching the
   existing file's discipline (`:92-105`) rather than pinning a Tailwind string.
3. The existing positive control (`qc-anomaly-patched-fixture`) still shows `Repaired`.
4. The existing `qc-anomaly-fixture` and `testpass2` assertions still pass unchanged.
5. No live literal renders as raw snake_case.
6. `npx tsc --noEmit`, `npm run lint`, `npx playwright test` all green.

## Fixtures

`dashboard/e2e/fixtures/` holds hand-written `run_record.json` files, registered in
`dashboard/e2e/fixtures.ts`. Existing `repair_history` entries must gain `patch_applied`
**explicitly** — an omitted key would make an assertion pass vacuously (RISK-5). Add one new
fixture for the rejected-patch case.

## Dependencies and sequencing

Depends on `patch-applied-field` (the engine must emit the field, and the fixtures must mirror
what it emits). Independent of the other two siblings.

## Risks specific to this aspect

- Fixtures are hand-written, so they can drift from what the engine actually produces; keep
  them faithful to the Python model.
- The dashboard is structurally typed and tolerant, so a missing field is `undefined` and
  falsy — which silently reads as "not applied". Explicit fixture values are what prevent a
  vacuous pass.
- `AGENTS.md` in `dashboard/` warns this is **not** the Next.js in your training data — read
  `node_modules/next/dist/docs/` before writing framework-level code.
