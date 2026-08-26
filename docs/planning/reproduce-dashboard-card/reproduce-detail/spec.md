# Spec: reproduce-detail

Aspect of `reproduce-dashboard-card` · the per-run audit surface.

## Problem slice & user outcome

A reviewer can open one reproduction and audit it end-to-end: exactly which
claims reproduced (with stated vs observed values and deltas), what the engine
repaired, which bytes were pinned (commit, tree hash, requested rev), whether
the bundle is signed, and a downloadable copy of the whole bundle for offline
audit. Outcome: the C8 verdict becomes a shareable, reviewable artifact.

## In-scope requirements

- **D1 — `/reproduce/[id]` page**: Server Component, `force-dynamic`; reads
  `reproduce_record.json` + `reproduce.json` via the list aspect's lib;
  `notFound()` when no bundle (mirroring the run detail page).
- **D2 — Header**: reproduce id, derived overall status badge (shared from the
  list aspect), repo/source_url, run command, created_at, exit_code
  (non-zero presented honestly, never as a pass).
- **D3 — Provenance block**: `source_url`, `source_commit`,
  `source_tree_sha256` (mono, middle-truncated, full value on title —
  provenance-panel convention), `requested_rev` from the manifest labelled as
  invocation metadata (it lives in the unsigned `reproduce.json`), and
  `claims_sha256`.
- **D4 — Claims table**: id, status badge, claimed, observed, tolerance,
  delta, message (verbatim engine wording — do not editorialize freshness /
  unresolved-locator messages).
- **D5 — Repair history**: `repair_history` rendered as env-repair lines
  (outcome, `patch_applied`, install op, detail) in the repair-timeline mould.
- **D6 — Signature presence**: `signature.json` existence shown (algo +
  public_key fingerprint); no verification computation this slice.
- **D7 — Bundle download**: API route, **GET and read-only** (mirror the
  first-party export route: no writer gate, all reproduce runs are visible to
  any viewer per the PRD decision), serving the bundle's JSON files as
  attachments: `?file=record|manifest|signature` (allowlist param) →
  `reproduce_record.json` / `reproduce.json` / `signature.json` bytes with
  `Content-Disposition: attachment`. **No zip, no new dependency** — the
  dashboard has no zip lib and the export precedent is single-file downloads;
  the signed record itself is the auditable artifact (the `source/` tree is
  attested by `source_commit` + `source_tree_sha256`, not downloaded). Strict
  id validation (mirror `InvalidRunIdError` → 400), 404 on missing file/dir,
  400 on an unknown `file` value.

## Out-of-scope boundaries

- No signature verification, no claim re-evaluation, no promote/curation UI.
- No launch form, no DOI/PDF, no figure/plot claims.
- No engine changes (no `contig show` extension; the dashboard reads the
  bundle directly).

## Acceptance criteria (testable)

- A1. E2E: fixture bundle (mixed claim statuses + repair_history +
  signature.json + source/) → detail page renders all sections; each claim's
  status badge matches its record literal.
- A2. Unknown id → 404 page, not a crash.
- A3. Download route returns the requested file as an attachment
  (`?file=record` → `reproduce_record.json` bytes); 404 for a nonexistent id;
  400 for an unknown `file` value; `signature` only when `signature.json`
  exists.
- A4. Non-zero-exit fixture → header shows the honest "did not complete"
  presentation and every claim renders `unverified`, never a pass.
- A5. Freshness-`unverified` claim message renders verbatim.

## Dependencies & sequencing

- After the list aspect (consumes its lib + badge variants).
- Check the first-party export route mechanism (`app/api/runs/[id]/export/`)
  during planning; mirror it (dependency decision only if it uses a non-stdlib
  zip lib).

## Open questions / risks

- Zip mechanism unknown until the export route is read (risk: new dependency).
- `requested_rev` labelling — must not be presented as attested.