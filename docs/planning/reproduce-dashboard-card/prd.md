# PRD: Reproduce Dashboard Card

| | |
|---|---|
| Slug | `reproduce-dashboard-card` |
| Branch | `feat/reproduce-dashboard-card/aliz` |
| Status | Draft (pre prd-generator critique) |
| Sources | `docs/planning/_card/issue.md` (inline brief), `docs/planning/_card/understanding.md` (dig), CAPABILITY_ROADMAP.md C8 |

## Problem Statement

The C8 track — `contig reproduce`, the engine that runs a third-party published
repo and reports per-claim `REPRODUCED` / `WITHIN-TOLERANCE` / `DIVERGED` /
`UNVERIFIED` verdicts in a signed, re-runnable bundle — is 12 slices deep on the
CLI and **invisible in the dashboard**. The original C8 build surface named
"CLI + dashboard card, community-facing and free"; the card was deferred in
every C8 slice. Today a reproduce verdict exists only as terminal output; there
is no enumeration of reproduce runs anywhere (`contig list` and the dashboard
runs list both scan only `run_record.json` dirs and silently skip reproduce
bundles). The C8 "why it is moat" #2 — "I ran 50 published papers' code — here
is how many reproduced" as the cheapest acquisition channel — is unreachable
without a surface.

Who it is for: the same dashboard users (lone computational biologist, wet-lab
scientist who can't code) plus the community-facing audience C8 targets. The
status quo cost: a finished, signed reproduction claim is not reviewable,
shareable, or browsable; the feature's acquisition value is dormant.

## Goals & Success Metrics

1. **Browseable:** every `contig reproduce` bundle under the runs dir is listed
   on a dedicated `/reproduce` page with a derived overall status. Success:
   `listReproduceRuns` returns every dir containing `reproduce_record.json`;
   E2E covers a 3-record fixture set.
2. **Honest verdicts:** per-claim statuses render with the exact shipped
   semantics — lowercase record literals mapped to labeled, colored badges,
   color never the sole signal, `unverified` never rendered as reproduced.
   Success: E2E fixture with one of each status renders correctly; a
   non-zero-exit record (all claims `unverified`) renders as such.
3. **Auditable:** per-run detail shows claims, repair history, provenance
   (repo / URL / commit / tree hash), signature presence, and a bundle download
   (zip of the run dir). Success: download route returns a zip containing
   `reproduce_record.json` + `reproduce.json` (+ `signature.json` when
   present).
4. **Zero engine change:** the Python core, `models.py`, and the CLI are
   untouched. Success: `git diff` over `src/` is empty.

Measured by the E2E suite (`npm test` in `dashboard/`) with fixtures in
`e2e/fixtures/reproduce-*/`; no synthetic benchmark needed. **Honest caveat:**
the acquisition-channel outcome (community reach) is unmeasurable at this
stage — the E2E correctness bar is the proxy, and no organic reproduce volume
exists yet (risk 5).

## User Personas & Scenarios

- **Community reader** (target of C8's acquisition play): opens `/reproduce`,
  sees a table of published-paper reproductions with statuses and links; reads
  a detail page to see exactly which claims reproduced, with stated vs observed
  values and deltas.
- **Reviewer / third-party verifier**: opens a detail page, checks the signed
  bundle (`signature.json`, tree hash, commit pin), downloads the zip for
  offline audit. No Contig account state is required — reproduce records carry
  no `owner.json`, so all runs are visible to any viewer.
- **Researcher wanting to run their own**: sees the empty state / CLI-guidance
  note ("run `contig reproduce <repo> --run ... --claims ...`") and copies the
  example. The launch form is explicitly deferred.

## Requirements

### Must-have

- **R1 — `/reproduce` listing page.** Server Component (`force-dynamic`, the
  runs-list convention) reading `reproduce_record.json` + `reproduce.json` from
  `<runsDir()>/<id>/`; renders every reproduce bundle found (no ownership
  filter). Columns: reproduce id (mono link), repo (or source_url), run
  command (truncated), created_at, derived overall status badge, per-status
  claim counts. Empty state when none.
- **R2 — Derived overall status.** No reduced verdict exists on the record
  (only per-claim statuses + `exit_code`); derive client-side, worst-of,
  mirroring the runs-table convention (fail > warn > unverified > pass):
  `diverged` > `within_tolerance` > `unverified` > `reproduced` (unknown
  literal counts as `unverified`, never a pass); a non-zero `exit_code`
  surfaces as its own "did not complete (exit N)" presentation, never as a
  pass. Pinned by pure-function tests in the E2E/unit-visible lib layer.
- **R3 — Claim status badges.** New badge variant set for the four claim
  literals (`reproduced`, `within_tolerance`, `diverged`, `unverified`),
  following the StatusBadge contract (icon + label + color; color never the
  sole signal). Existing `pass/warn/fail/unverified` mapping untouched.
- **R4 — `/reproduce/[id]` detail page.** Per-run view: run metadata (repo,
  run command, interpreter, created_at, exit_code), provenance block
  (source_url, source_commit, source_tree_sha256 with mono/middle-truncated
  hashes per the provenance-panel convention, `requested_rev` from
  `reproduce.json`), per-claim table (id, status badge, claimed, observed,
  tolerance, delta, message), repair history (env-repair lines with
  `patch_applied`), signature presence, and a **bundle download** button.
  Not-found behavior mirrors the run detail page (`notFound()`).
- **R5 — Bundle download.** Read-only GET API route (the first-party export
  route's pattern — no writer gate: reproduce runs are visible to any viewer)
  serving the bundle's JSON files as attachments via an allowlist param
  (`?file=record|manifest|signature` → `reproduce_record.json` /
  `reproduce.json` / `signature.json`). **No zip and no new dependency** — the
  dashboard has no zip lib; the signed record is the auditable artifact, and
  the `source/` tree is attested by `source_commit` + `source_tree_sha256`,
  not downloaded. Strict id validation (mirror `InvalidRunIdError` → 400),
  404 on missing, 400 on unknown `file`.
- **R6 — CLI guidance.** A "How to reproduce a published paper" note on the
  listing page (and/or empty state) with the canonical command and pointers to
  `extract-claims`; explicitly read-only — no launch form this slice.
- **R7 — Nav entry.** `Reproduce` added to `site-nav.tsx` LINKS.

### Should-have

- **S1 — Pending-cases teaser.** A line/count from
  `pending_reproduce_corpus.jsonl` (read-only) noting cases awaiting review,
  linking to the CLI promote path. Small; skip if it complicates the slice.
- **S2 — Sort/filter** on the listing table (by overall status), mirroring
  runs-table conventions.

### Nice-to-have

- **N1 — Signature verification state** (recompute/verify the Ed25519 sig in
  the UI) — deferred; render presence only.

## Technical Considerations

- **Read model (no engine change):** dashboard reads bundles from disk via
  `lib/runs.ts` (its standing convention; `runsDir()` = `CONTIG_RUNS_DIR` or
  repo-root `runs/`). New functions mirroring `listRuns`/`readRecord`:
  `listReproduceRuns`, `readReproduceRecord`, `readReproduceManifest` —
  reading `reproduce_record.json` / `reproduce.json` from
  `<runsDir()>/<id>/`, skipping dirs without the record. Bundle JSON shapes are
  already serialized by the Python side (`bundle.py:73-129`); the dashboard
  adds its own TS types (no shared schema exists).
- **Status literals** are lowercase in the record (`models.py:797`): map
  `reproduced` → emerald/CheckCircle, `within_tolerance` → blue/Info,
  `diverged` → red/XCircle, `unverified` → slate/HelpCircle (existing
  StatusBadge MAP has no blue variant — add one, keeping icon+label+color).
- **Record fields available** (verified): `reproduce_id`, `repo`,
  `run_command`, `claims_sha256`, `claim_results[{id,status,claimed,observed,
  tolerance,delta,message}]`, `exit_code`, `created_at`, `interpreter`, `tool`,
  `repair_history[]`, `source_url`, `source_commit`, `source_tree_sha256`;
  manifest adds `requested_rev`. No `locator` persisted on results.
- **Forward-compat is load-bearing** (critique gap): bundles are written by
  whatever contig version the user runs — possibly newer than this dashboard.
  TS types must tolerate unknown fields (no strict excess-property rejection on
  parse), and an **unrecognized claim status literal** must render a neutral
  "unknown" badge, never crash or fail the page. The worst-of derivation treats
  an unknown literal as `unverified` (honest, never a pass).
- **Zip export:** node `archiver` not currently a dependency — check
  `dashboard/package.json`; prefer stdlib `fs`+`tar`/manual zip or reuse the
  first-party export route's exact mechanism (whatever it uses; mirror it).
- **Verification/reproducibility impact:** none to the engine; the card
  renders hashes and claim diffs only, no raw reads leave the machine. The
  freshness guard's semantics must be preserved in presentation — a
  freshness-`unverified` claim is the correct outcome for committed-output
  repos, and the UI must not imply otherwise.
- **Dashboard testing:** Playwright only (no unit runner). Fixtures under
  `e2e/fixtures/reproduce-*` registered in `e2e/fixtures.ts` (installed by
  `e2e/global-setup.ts`), spec files under `e2e/`. Pure logic (worst-of
  derivation, status mapping) should be colocated in a lib module written to be
  unit-observable (the `lib/ownership.ts` precedent) even if exercised via E2E.

## Risks & Open Questions

- **Zip dependency** — **resolved at planning**: the first-party export route
  is a single-file JSON download (no zip lib in the dashboard), so the
  download surface is single-file attachments with no new dependency.
- **Status ordering** — worst-of ordering is a product decision
  (`diverged > within_tolerance > unverified > reproduced`, mirroring the
  runs-table verdict order); a run with 3 reproduced + 1 unverified shows
  "unverified" overall, which is honest but may read harsh; the counts column
  mitigates. Flagged, not papered over.
3. **Freshness semantics in UI copy** — unverified claims carry specific
   reasons (committed output, non-zero exit, unresolved locator); the message
   field is per-claim and shown verbatim. Keep engine wording, do not
   editorialize.
4. **`requested_rev` lives only in `reproduce.json`** (unsigned) — display it
   with the provenance block labelled as invocation metadata, not attested.
5. **No real-world reproduce volume** — push, not demand-pull; the E2E
   fixtures are the only data. Fine for a read-only surface; revisit when
   organic runs exist.

## Out of Scope

- **Launch form / dispatch from the dashboard** (`contig reproduce` executes
  arbitrary shell — trust surface; deferred follow-on).
- **DOI/PDF intake**, figure/plot claims (hard-blocked), `extract-claims`
  integration.
- **Corpus curation UI** (pending review / promote) — CLI-only today.
- **Engine changes of any kind**: no `models.py`, no new CLI command (e.g. no
  `contig show` extension for reproduce records — the dashboard reads the
  bundle directly), no signature verification computation.
- **First-party reproduce/compare pages** — untouched.
- **Owner filtering** — reproduce records carry no `owner.json`; all runs are
  visible to any viewer (shared/community artifacts).

## Guardrails

Layer-2 surface only ✓ · research-use computation-vs-numbers verdicts, never
paper conclusions or clinical claims ✓ · no raw-read egress (hashes + claim
diffs + metadata only) ✓ · honesty: `unverified` never rendered as reproduced,
no over-claiming of the signed bundle's meaning ✓ · test-first (Playwright
fixtures before page code) ✓.