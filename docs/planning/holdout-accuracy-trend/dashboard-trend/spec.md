# Aspect spec: dashboard-trend

Parent PRD: `../prd.md`. Aspect 3 of 3. **Depends on `history-store`** (the two JSONL
files + their format). Independent of `guard-cli` — can run in parallel with it.

## Problem slice & outcome

Surface the held-out-accuracy trend and the self-heal outcome-match trend on the `/eval`
page, mirroring the shipped detector `EvalHistory` (`eval-history.tsx`): a fixed-domain
`[0,1]` SVG sparkline + a snapshot table with per-version deltas, degrading to an empty
state when a history file is absent. This is the buyer-facing "how Contig is learning on the
**frozen** set" evidence.

## In scope (R8)

- `dashboard/lib/types.ts`: add a `HealSnapshot` (+ `HealClassScore`) interface mirroring
  `src/contig/models.py` (`timestamp, scenario_count, corpus_sha, outcome_match_rate,
  recovery_rate, per_class: Record<string,HealClassScore>, covered_classes, contig_version`).
  Reuse the existing `EvalSnapshot` for holdout.
- `dashboard/lib/runs.ts`: `getHoldoutHistory()` → `EvalSnapshot[]` from
  `holdout_history.jsonl` (env override `CONTIG_HOLDOUT_HISTORY`); `getHealHistory()` →
  `HealSnapshot[]` from `heal_history.jsonl` (env override `CONTIG_HEAL_HISTORY`). Both mirror
  `getEvalHistory()` (file order, skip blank/malformed, `[]` when absent).
- Components (Server Components) mirroring `eval-history.tsx`:
  - `HoldoutHistory` — same `EvalSnapshot` shape, relabeled "Held-out accuracy over time",
    "held-out N", copy referencing `contig eval-guard --snapshot`, aria-label "Held-out
    detector accuracy over time".
  - `HealHistory` — sparkline over `outcome_match_rate` ([0,1]) + a snapshot table
    (When / Scenarios / Outcome-match / Delta / Recovery / Version), heading "Self-heal
    outcome-match over time".
- `dashboard/app/eval/page.tsx`: fetch both in the `Promise.all`, render `<HoldoutHistory>`
  and `<HealHistory>` after `<EvalHistory>` in **both** the `!report` and normal branches.
- e2e: fixtures `_holdout_history/holdout_history.jsonl` + `_heal_history/heal_history.jsonl`
  (≥2 points each so deltas render), extend `installFixtures`/`removeFixtures`
  (backup→swap→restore, mirroring the eval-history handling), and a spec
  `holdout-heal-trend.spec.ts` asserting structure + a `pp` delta for each series.

## Out of scope

- Modifying `eval-history.tsx` / the detector trend (leave the tested component untouched;
  new components may duplicate the small Sparkline/DeltaCell or import a new shared
  `trend-primitives.tsx` — the agent's call, but do not destabilize the existing trend).
- Any new API route (the page reads the committed JSONL server-side, like `getEvalHistory`).
- A combined "eval health" unified panel (PRD nice-to-have).
- Any CLI change (aspect `guard-cli`).

## Acceptance criteria (testable)

1. `npm run build` succeeds.
2. `npm test` (Playwright) green, including the new spec: `/eval` shows the "Held-out
   accuracy over time" heading + its sparkline (by aria-label) + a `pp` delta; and the
   "Self-heal outcome-match over time" heading + its sparkline + a `pp` delta.
3. Absent-file path: with the fixtures **not** installed (or an empty file), the two sections
   render their empty state, not an error. (Assert via a spec that points the env override at
   an absent path, or reuse the existing teardown ordering.)
4. Existing `/eval` specs (`eval-history.spec.ts`, `detector-compare.spec.ts`) still pass —
   the detector trend is unchanged.

## Dependencies & sequencing

Inbound: `history-store` (file format + committed seeds so the page renders non-empty by
default). Parallelizable with `guard-cli`.

## Open questions / risks

- **Next.js version warning:** `dashboard/AGENTS.md` says "This is NOT the Next.js you know —
  read `node_modules/next/dist/docs/` before writing any code." The agent MUST read the
  relevant guide (Server Components, `searchParams`) before editing `page.tsx`.
- Heal `per_class` is `{matched,total,rate}` (no precision/recall) — the per-class table is a
  should-have; must-have is the sparkline + snapshot table + delta + empty state.
