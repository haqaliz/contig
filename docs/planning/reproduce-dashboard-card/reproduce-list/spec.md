# Spec: reproduce-list

Aspect of `reproduce-dashboard-card` · the browseable listing surface.

## Problem slice & user outcome

A visitor can see every third-party `contig reproduce` run on their machine at a
glance: which papers/repos were checked, their derived overall status, and
per-status claim counts — with a path into per-run detail. Outcome: the C8
"community-facing" surface exists as a page, not terminal output.

## In-scope requirements

- **L1 — Read layer** (`lib/runs.ts` or a new `lib/reproduce.ts`, server-only):
  `listReproduceRuns()` enumerates `<runsDir()>/*/reproduce_record.json`
  (mirroring `listRuns`'s skip-without-record semantics, but for the reproduce
  record filename); `readReproduceRecord(id)` and `readReproduceManifest(id)`
  return typed shapes (TS types mirroring the Python-serialized bundle —
  `ReproduceRecord`, `ReproduceManifest`, `ClaimResult`-shaped). Malformed JSON
  → skip/`null` like `readRecord`, never a page crash.
- **L2 — `/reproduce` page**: Server Component, `force-dynamic`, `PageHeader`
  ("Reproductions" + actions), table of runs sorted by `created_at` desc.
  Columns: id (mono, link to `/reproduce/[id]`), repo (URL or path), run
  command (truncated), created, overall status badge, claim counts
  (e.g. "2 reproduced · 1 diverged"). Empty state when no bundles found.
- **L3 — Derived overall status** (pure, unit-observable lib function, the
  `lib/ownership.ts` precedent): worst-of over per-claim statuses, mirroring
  the runs-table convention (fail > warn > unverified > pass):
  `diverged` > `within_tolerance` > `unverified` > `reproduced` (an unknown
  literal counts as `unverified` — honest, never a pass); a non-zero
  `exit_code` renders as its own "did not complete (exit N)" presentation
  rather than a claim-status badge (never a pass).
- **L4 — Claim-status badge set**: new badge variants for the four lowercase
  record literals, mapping 1:1 onto the existing palette semantics —
  `reproduced` (emerald, CheckCircle2, mirror pass), `within_tolerance`
  (amber, AlertTriangle, mirror warn), `diverged` (red, XCircle, mirror fail),
  `unverified` (slate, HelpCircle, mirror unverified) — following StatusBadge's
  icon+label+color contract; existing `pass/warn/fail/unverified` mapping
  untouched. Shared with the detail aspect.
  **Unknown literal → neutral "Unknown" badge, never a crash** (forward-compat
  from the PRD critique).
- **L5 — Nav entry**: `Reproduce` in `site-nav.tsx` LINKS.
- **L6 — CLI guidance**: "How to reproduce a published paper" note with the
  canonical command (`contig reproduce <repo> --run "<cmd>" --claims <file>`
  …) and a pointer to `contig extract-claims`; shown on the page (empty state
  and/or a footer card). Read-only — no form.

## Out-of-scope boundaries

- No launch/dispatch form; no claims editing.
- No detail view (aspect `reproduce-detail`), no zip download, no pending
  corpus UI.
- No changes to the runs list, compare page, or first-party reproduce actions.

## Acceptance criteria (testable)

- A1. E2E fixture set of 3 reproduce bundles (mixed statuses incl. a
  non-zero-exit record) → `/reproduce` lists all 3, none appear in `/runs`.
- A2. Overall badge derivation unit-observable: pure function pinned for each
  ordering case incl. empty claims and non-zero exit.
- A3. Empty state renders when `listReproduceRuns` returns `[]`.
- A4. Nav shows the Reproduce link; click lands on `/reproduce`.
- A5. Malformed `reproduce_record.json` in one fixture dir → skipped, no crash.
- A6. Fixture with an **unknown status literal** → neutral badge rendered,
  page still renders all other claims.

## Dependencies & sequencing

- First aspect (the detail aspect consumes its lib + badge components).
- No Python changes anywhere.

## Open questions / risks

- Sort order default: `created_at` desc (string ISO — sortable).
- Truncation: run command may be long; title-hover full value (provenance-panel
  precedent).