# Aspect spec: failure-classes

Slug: `eval-corroboration-fold-in` · Aspect: `failure-classes`

## Problem slice

Close the dashboard relabel-taxonomy drift: `FAILURE_CLASSES`
(dashboard/lib/derive.ts:278-292) lists 13 of the 18 `FailureClass` literals,
so the pending-review relabel UI cannot correct a provisional label for
`reference_not_bgzf`, `missing_dependency`, `disk_full`, `download_failed`, or
`permission_denied` — all reachable since v0.49-0.50. This blocks the
human-correction channel that the C6 fold-in's verification corpus reuses
(PRD R6).

## In-scope

- `FAILURE_CLASSES` covers all 18 literals in the same order as
  `src/contig/models.py:262-281`.
- Route validation (dashboard/app/api/corpus/promote/route.ts) accepts the new
  labels (it already validates against `FAILURE_CLASSES`, so no route change
  beyond the list).
- Tests pin `18` and a relabel round-trip for a previously-missing class.

## Out-of-scope

- Python-side changes (the CLI accepts all 18 already); verification-case UI
  (aspects 1-3); any styling.

## Acceptance criteria

1. `FAILURE_CLASSES.length === 18`, one entry per `FailureClass` literal.
2. POST /api/corpus/promote with `label: "disk_full"` passes validation
   (and a unit test asserts the validation path accepts a previously-missing
   label without a 400).
3. Existing dashboard tests (tsc, lint, e2e) stay green.

## Dependencies / sequencing

Independent of aspects 1-3 — can be built in parallel. Needs the dashboard
test/build commands (`npx tsc --noEmit`, `npm run lint`, `npx playwright test`).
