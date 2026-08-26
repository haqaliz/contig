# Understanding — reproduce-dashboard-card

Phase-2 dig note (two parallel explore agents, graphify-first). Grounds the PRD
interview. All file:line refs verified in the worktree.

## What the work is really asking

Surface the shipped third-party `contig reproduce` track (C8) in the dashboard:
list third-party reproduce runs, show per-claim verdicts, repair history, and
the signed bundle — plus a reproduce entry point. The C8 roadmap deferred "a
dashboard card" in every slice (CAPABILITY_ROADMAP.md C8); this closes it.
**Read-only over shipped machinery: no engine contract change, no `models.py`
change, no new CLI command** (dashboard reads bundles from disk directly, its
standing convention).

## What exists today (verified)

### Engine side (Python)
- Bundle layout: `<runs-dir>/<reproduce_id>/` with `reproduce_record.json`
  (full `ReproduceRecord`), `reproduce.json` (re-runnable manifest:
  `reproduce_id`, `repo`, `run_command`, `claims_sha256`, `created_at`,
  `source_url`, `source_commit`, `source_tree_sha256`, `requested_rev`),
  optional `signature.json` (Ed25519, opt-in via `CONTIG_SIGNING_KEY`), and
  `source/` (fetched remote checkouts) — `bundle.py:73-129`.
- `ReproduceRecord` (`models.py:812-831`): `reproduce_id`, `repo`,
  `run_command`, `claims_sha256`, `claim_results: list[ClaimResult]`,
  `exit_code`, `created_at`, `interpreter`, `tool`, `repair_history:
  list[RepairStep]`, `source_url`, `source_commit`, `source_tree_sha256`.
- `ClaimResult` (`models.py:800-809`): `id`, `status`, `claimed`, `observed`,
  `tolerance`, `delta`, `message`. **Status literals are lowercase**:
  `"reproduced" | "within_tolerance" | "diverged" | "unverified"`
  (`models.py:797`). **No locator field is persisted** — locators exist only on
  the input `Claim` dataclass.
- **No overall reproduce verdict exists** — only per-claim statuses plus
  `reduce_reproduction` counts/summary (`verification/reproduce.py:1447-1467`).
  A non-zero `exit_code` short-circuits every claim to `unverified`
  ("run did not complete (exit N)").
- **No enumeration of reproduce runs exists anywhere** — `contig list`
  (`workspace.py:39-51`) scans only `run_record.json` dirs; `contig show
  <reproduce_id>` fails (`load_run` requires `run_record.json`). The dashboard
  must scan `<runs-dir>/*/reproduce_record.json` itself (mirroring
  `list_run_ids`).
- Capture channel exists: `<runs-dir>/pending_reproduce_corpus.jsonl` +
  `reproduce-case-promote` (curation — a write surface, out of scope here).

### Dashboard side (Next.js)
- **Zero awareness of the third-party feature** — no route, component, or type
  references `claim_results`/`reproduce_id`/`source_url`; the only
  "reproduce" hits are the FIRST-PARTY per-run "Reproduce exactly" action
  (`app/api/runs/[id]/reproduce/route.ts` + `components/run/reproduce-actions.tsx`,
  dispatches a re-run from `launch.json` — unrelated to `contig reproduce`).
- Data flow: server components read engine artifacts from disk via `lib/runs.ts`
  (`runsDir()` = `CONTIG_RUNS_DIR` or `../runs`); CLI shell-outs for actions.
  Read-only data = direct fs read; no HTTP backend (`dashboard/README.md:5-9`).
- Conventions (from the dig): `force-dynamic` server page → `PageHeader` +
  client table; `StatusBadge` maps pass/warn/fail/unverified only — a new
  reproduced/diverged/within_tolerance/unverified set needs a new badge variant
  (color is never the sole signal); nav entries in `components/site-nav.tsx`
  LINKS; write routes need `requireWriter()` + `proxy.ts` regex update;
  Playwright-only tests with fixtures in `e2e/fixtures/` registered in
  `e2e/fixtures.ts`, installed by `e2e/global-setup.ts`; graceful-degradation
  pattern on `/eval` ("Live eval not available" card when CLI missing).
- Export precedent: `app/api/runs/[id]/export/route.ts` (first-party bundle
  export) — mirror for reproduce bundle download.
- Launch precedent: `app/runs/new/page.tsx` + `launch-form.tsx` + dispatch
  route (spawns `uv run contig` detached) — the model for any reproduce entry
  point, with one caveat: `contig reproduce --run "<cmd>"` executes an
  arbitrary shell command on the user's compute, a larger trust surface than a
  pipeline dispatch.

## Scope boundaries (honest, from the brief + docs)

- **Not in scope:** figure/plot claims (hard-blocked, stdlib-only),
  PDF/DOI intake, extract-claims integration into the UI, corpus
  promote/curation UI, first-party reproduce changes, engine/CLI changes.
- **In scope by brief:** listing + per-claim verdicts + repair history +
  signed-bundle access + "a reproduce entry point".
- The card must render `unverified` honestly (freshness-guarded committed-output
  repos, non-zero exits) — never as a pass.

## Open questions for the interview

1. **Surface shape**: a dedicated `/reproduce` page (nav entry) vs a card on
   `/runs` vs a tab/section. The C8 wording is "a dashboard card"; a separate
   page matches the "community-facing" framing and avoids crowding the runs
   list. (Recommend: dedicated page, card-styled sections per run.)
2. **Entry point depth**: (a) read-only list + view (entry point = link to CLI
   docs), (b) minimal "New reproduce" form (repo, run command, claims JSON
   paste, `--allow-fetch`/`--allow-install`/`--rev` toggles) dispatching via
   CLI spawn, or (c) full form with claims-file upload. Scope/trust question —
   `--run` executes arbitrary shell; recommend (b) minimal with explicit
   warnings, or defer the form entirely to a follow-on slice.
3. **Status vocabulary**: new badge set for the four claim statuses — mapping
   proposal: reproduced=emerald, within_tolerance=blue/info, diverged=red,
   unverified=slate (the existing StatusBadge map has no blue — check).
4. **Bundle download**: zip the whole run dir (record+manifest+signature+source)
   vs a single-file JSON export of the record. Mirror first-party export?
5. **Overall run status**: no reduced verdict exists in the record — derive one
   client-side from claim statuses + exit_code (worst-of), or add nothing and
   show per-claim only? (Recommend worst-of badge derived client-side; no model
   change.)
6. **Auth/owner**: reproduce records have no `owner.json` — do we show all
   reproduce runs to any viewer, or skip ownership filtering (note first-party
   list filters by owner)?

## Guardrails check (CLAUDE.md)

Layer-2 surface only ✓ (reproduce/verify verdicts — never Layer 1) · no clinical
or scientific-judgement claims (per-claim verdicts are computation-vs-numbers,
never paper conclusions) ✓ · no raw-read egress (cards render hashes/metadata
only; `source/` checkout stays local) ✓ · honesty: UNVERIFIED never rendered as
REPRODUCED ✓ · test-first (Playwright fixtures for the dashboard, per its
conventions; no Python change expected) ✓.