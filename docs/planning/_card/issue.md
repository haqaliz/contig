# Unit of Work -- reproduce-dashboard-card

> Inline brief (source: contig-next handoff, 2026-08-26). No GitHub issue exists
> for this slug; the branch `feat/reproduce-dashboard-card/aliz` and the PR carry
> the id.

## Brief

Build the long-deferred C8 dashboard card (deferred in every C8 slice; the
original C8 surface was "CLI + dashboard card, community-facing and free"): a
dashboard section listing third-party `contig reproduce` runs with per-claim
verdicts (REPRODUCED / WITHIN-TOLERANCE / DIVERGED / UNVERIFIED), repair history,
and a signed-bundle download, plus a reproduce entry point. Read-only over the
shipped `ReproduceRecord`/`ClaimResult`/`ReproduceScenario` machinery -- no engine
contract change, no `models.py` change, fixture-driven tests.

Caveat to honor: render honestly and scoped -- no figure/plot claims
(hard-blocked, stdlib-only), no DOI/PDF intake, drafts from `extract-claims`
still need user review, and freshness-guarded `UNVERIFIED` is the correct answer
for committed-output repos; do not build a "paste a DOI" flow. Check how
`dashboard/app/api/runs/[id]/reproduce/route.ts` and
`components/run/reproduce-actions.tsx` handle first-party reproduce before
deciding the third-party surface shape.

## Cited context (docs/technical/CAPABILITY_ROADMAP.md)

- C8 header: "…remote `https://` git-URL intake slice 6 SHIPPED (Unreleased) +
  `--rev` revision pinning slice 7 SHIPPED (Unreleased) + checkout-tree hash
  slice 8 SHIPPED (Unreleased) + local tree hash slice 9 SHIPPED (Unreleased) +
  paper-claim extraction (`contig extract-claims`) SHIPPED (Unreleased)…"
- Original C8 build surface: "A `contig reproduce <repo|doi>` surface (CLI +
  dashboard card), community-facing and free."
- Every C8 slice's deferral list names "a dashboard card" (slices 1, 1.5, 2, 3,
  4, 5, freshness guard, 6, 7, 8, 9, extract-claims, reproduce-guard fold-in).
- C8 "why it is moat" #2: "the cheapest acquisition channel we have (Principle
  #5). 'I ran 50 published papers' code -- here is how many reproduced, and why'
  is Biostars / r/bioinformatics / nf-core reputation in a bottle, and a free,
  viral top-of-funnel that feeds paying Layer-2 usage."
- Shipped machinery to surface: `contig reproduce <repo> --run --claims`
  (v0.40.0), locators (JSON/TSV/CSV/stdout/notebook), freshness guard (all
  binding surfaces), env resurrection (`--allow-install`), remote intake
  (`--allow-fetch`, `source_url`/`source_commit`), `--rev` pinning, tree hashes
  (`source_tree_sha256`), `extract-claims` (draft + review sidecar), signed
  bundle, `reproduce-guard` (fourth C6 guard, baseline 13/14), pending
  `ReproduceCase` capture + `reproduce-case-promote`.
- Standing C8 deferrals NOT in scope for the card: PDF/DOI resolution, figure /
  plot / table-image claims (hard-blocked -- no plot-hash, stdlib-only
  dependency contract), checkout pruning, private-repo credentials, submodules,
  locator niceties.

## Guardrails check

Layer-2 reproduce/verify surface, never Layer 1 ✓ · research-use only, never a
clinical or scientific-judgement verdict ✓ · no raw-read egress (the card shows
hashes, claim diffs, verdicts -- never reads) ✓ · honesty posture preserved:
UNVERIFIED is never rendered as REPRODUCED, committed-output repos must read
UNVERIFIED ✓ · test-first, stdlib-only Python core, dashboard follows its own
existing test/build patterns ✓.