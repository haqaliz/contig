# Card: feat reproduce-checkout-hash (C8, slice 8)

**Type:** feat · **Owner:** aliz · **Branch:** `feat/reproduce-checkout-hash/aliz`

No GitHub issue — this unit of work came from `/contig-next` (cn), 2026-07-24. The
recommendation below is the source brief.

## Brief

Add C8 slice 8 to `contig reproduce` — record a content hash of the checkout /
`source` tree on the `ReproduceRecord` so the bundle attests to the **bytes that
actually ran**, not merely the commit SHA that was nominally cloned. This closes
slice 6's explicitly-disclosed gap:

> "The checkout is evidence, not attestation: `_maybe_write_signature` signs the
> record only — the `source/` tree is unsigned and unhashed and can be modified
> afterwards with nothing detecting it, so the commit SHA is the attested fact and
> `source/` is a convenience copy for inspection… hashing the tree is deliberately
> a separate slice." — `docs/technical/CAPABILITY_ROADMAP.md:1373-1376`

Deferred-not-blocked, listed at `CAPABILITY_ROADMAP.md:1394` ("hashing or signing
the checkout tree").

## Design intent (from handoff — resolve in the dig)

- Deterministic digest over the repo-relative file list + per-file content
  (stdlib `hashlib`). Decide sort order and whether to exclude `.git/`.
- Prefer an **additive, unsigned** field (mirroring slice 7's `requested_rev`) so
  pre-slice-8 signed reproduce bundles keep verifying. The reproduce-bundle
  signature has already broken twice in two releases (slice 6 added
  `source_url`/`source_commit`; the somatic FAIL-floor changed `verdict`) — a third
  break is a real cost to weigh in the dig.
- Watch the ordering interaction with the run-start **freshness stamp** and the
  `--allow-install` retry: a retry mutates the tree, so hash timing must be pinned
  by test.

## Key open questions (resolve first in the dig)

1. **Signed vs unsigned placement.** Lean additive/unsigned like `requested_rev`
   (goes in `reproduce.json`, not the signed record) to avoid a third signature
   break — unless the dig finds attestation genuinely requires it in the signed
   payload. Decide explicitly.
2. **What gets hashed, and when.** Local-path repo (dirty by design, no SHA) vs
   fetched `source/` checkout. Hash timing relative to: clone/checkout, `--rev`
   targeted fetch, the run-start freshness stamp, and the `--allow-install`
   retry-once (which rewrites files). Is the hash "what was cloned" (pre-run) or
   "what ran" (which run — first or retried)? Pin by test.
3. **Tree-walk determinism & scope.** Sort order (repo-relative path sort),
   `.git/` exclusion, symlink handling, large-tree cost, and behaviour on an
   unreadable file — reuse the never-raising / honest-degradation posture of the
   locator readers.

## Why this was picked (from the `cn` ranking)

- **Closes the one disclosed integrity gap in the active C8 track.** Slices 6/7
  (v0.47.0/v0.48.0) existed to make the verdict "checkable by a third party"; a
  mutable, unattested `source/` tree undercuts exactly that. This is the missing
  piece of the slice-6/7 attestation arc.
- **On-thesis Layer-2 moat work.** Reproducibility integrity is a core `CLAUDE.md`
  requirement; the roadmap mantra is "make every verdict harder to fool"
  (`CAPABILITY_ROADMAP.md:1506`). A tree hash mismatching the recorded SHA is a new
  corpus signal (dirty/tampered checkout).
- **Crisp, unblocked, CI-observable.** stdlib-only (`hashlib`); and unlike every
  prior C8 slice ("no real git/network/repo in CI — reasoned, not observed"), this
  is genuinely testable in CI: fixture tree → hash → mutate → detect mismatch. No
  planning dir exists yet.

## Explicitly out of scope / do not touch

- **DOI resolution** — out of scope in C8; stays refused with a message that says so.
- **The disclosed slice-6 signature break** — pre-slice-6 signed reproduce bundles
  no longer verify; disclosed and pinned by a test. Do **not** "fix" it here, and do
  not introduce a *new* break lightly (see open question 1).
- Checkout pruning, private-repo credentials, submodules.
- Paper-parsing, figure/plot claims, remote `<doi|url>`, dashboard card, C6 eval
  fold-in — all unchanged deferrals.

## Alternates the `cn` run considered and ranked below this

- **C4 somatic cross-column swapped-pair smell test** (`CAPABILITY_ROADMAP.md:735,
  748`) — strong verification primitive, but the detection signal/design is less
  settled and somatic verify is still fixtures-only.
- **C8 reproduce dashboard card** — feeds the viral acquisition channel, but it's
  surface work, lower on the moat-depth axis.
- **C8 paper-parsing** — the bigger strategic prize, but an unresolved feasibility
  question (PDF dependency vs the stdlib-only contract, claim-alignment scope) — so
  ranked below a crisp, dependency-free slice.

## Grounding files

- `docs/technical/CAPABILITY_ROADMAP.md` — C8 section (esp. slice 6 disclosure
  `:1373-1376`, deferral `:1394`) + sequencing-summary C8 row.
- `CHANGELOG.md` §0.47.0/§0.48.0 — slices 6/7 as shipped, their honest limits, the
  signature-break disclosures, and the deferral list.
- `docs/planning/reproduce-remote-intake/` (slice 6) and
  `docs/planning/reproduce-rev-pin/` (slice 7) — the two most relevant prior PRDs/plans.
