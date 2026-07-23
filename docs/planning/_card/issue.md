# Card: feat reproduce-rev-pin (C8, slice 7)

**Type:** feat · **Owner:** aliz · **Branch:** `feat/reproduce-rev-pin/aliz`

No GitHub issue — this unit of work came from `/contig-next` (cn), 2026-07-23. The
recommendation below is the source brief.

## Brief

Add `--rev <ref>` to `contig reproduce` so the recorded `source_commit` pin from C8 slice 6
becomes **replayable**, not just auditable. Today nothing in the product consumes
`source_commit` (`CHANGELOG.md:114` — "the pin is auditable, not yet replayable… only a human
can act on it (`git checkout <sha>`)").

`--rev` takes a full SHA, tag, or branch; is only legal alongside an `https://` URL +
`--allow-fetch`; is validated/refused **before anything is written** (the same
no-bundle-no-litter contract as slice 6); and the resulting `source_commit` must equal the
requested revision when a full SHA was given.

## Key design risk (resolve first in the dig)

`--depth 1` cannot check out an arbitrary SHA. The fetch shape must change — `git init` +
`git fetch --depth 1 origin <rev>` + `git checkout FETCH_HEAD` — and that path depends on the
remote enabling `uploadpack.allowReachableSHA1InWant`. GitHub enables it; many self-hosted
remotes do not. **Decide explicitly** between a full-clone fallback and an honest refusal.
Keep the existing leading-dash-refused-first argv safety.

## Verification caveat

CI has no network (the `Fetcher` is injected; `default_fetcher` is asserted on for argv shape
only), so slice 6's wiring-vs-invocation gap applies here too — slice 6 shipped a real bug a
green suite missed (the relative-`--runs-dir` clone failure, `CHANGELOG.md:105`). Plan a
**manual real-clone smoke test** against a public repo, including the still-pending slice-6
one, before calling this done.

## Why this was picked (from the `cn` ranking)

- **It closes the loop slice 6 left open.** Slice 6 records *which revision of which repo*
  produced a verdict; `--rev` is what makes that record re-runnable — the difference between a
  provenance string and a reproducibility guarantee.
- **It is the named next deferral, not an invention.** `CAPABILITY_ROADMAP.md:1466` (C8 row)
  and `CHANGELOG.md:123` both list "`--rev`/tag/branch selection" first in the still-deferred
  set, with **no blocker attached** — unlike its neighbours (DOI resolution is out of scope by
  design; figure/plot claims need a plot-hash that would break the stdlib-only dep contract).
- **Pure Layer-2 moat work**: reproducibility infrastructure on the user's compute,
  stdlib-only, no new dependency, reusing the injected `Fetcher` seam.

## Explicitly out of scope / do not touch

- **DOI resolution** — explicitly out of scope in C8; stays refused with a message that says so.
- **The disclosed signature break** — pre-slice-6 *signed* reproduce bundles no longer verify
  (the canonical payload gained two `null` keys). Disclosed and pinned by a test; do **not**
  "fix" it in this slice.
- Checkout pruning, hashing/signing the checkout tree, private-repo credentials, submodules.
- Paper-parsing, figure/plot claims, dashboard card, C6 eval fold-in — all unchanged deferrals.

## Alternates the `cn` run considered and ranked below this

- C6 fold-in of C1/C3 signals into the eval corpus (`CAPABILITY_ROADMAP.md:908`) — real
  leverage, but its C7 sibling is blocked pending a labeling design, so scope is fuzzier.
- Checkout pruning / hashing the fetched tree (`CHANGELOG.md:120`) — real hygiene gap, but
  housekeeping rather than verdict-strength.
- Explicitly **not** picked: bwa-mem2 build+redirect — `CAPABILITY_ROADMAP.md:255` records it
  has **no live trigger** (sarek auto-builds the index; Contig exposes no flag to supply one).

## Grounding files

- `docs/technical/CAPABILITY_ROADMAP.md` — C8 section + sequencing-summary C8 row.
- `CHANGELOG.md` §0.47.0 — slice 6 as shipped, its honest limits, and the deferral list.
- `docs/planning/reproduce-remote-intake/` — slice 6 PRD + plan.
