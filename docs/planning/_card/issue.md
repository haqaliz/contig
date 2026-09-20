# Card — reproduce-locator-inference (feat)

Type: `feat` · id/slug: `reproduce-locator-inference` · owner: `aliz`
Branch: `feat/reproduce-locator-inference/aliz`
Worktree: `.claude/worktrees/feat-reproduce-locator-inference`
Source: **inline brief** (no GitHub issue — slug-scoped work, selected by `/contig-next`)

---

## Brief

Ship locator inference as the next C8 slice: given a repo path and a locator-less
draft from `contig extract-claims`, propose a locator per claim by searching the
repo's candidate output artifacts (JSON, TSV/CSV, `.ipynb`, text/log) for the claim's
stated value, reusing the shipped `resolve_pointer` / `resolve_cell` /
`resolve_match` / notebook resolvers **in reverse** rather than writing new parsers.

Be strict on ambiguity exactly as slice 4's pattern locator is: 0 or >1 candidate
sites means emit **NO** locator and leave the claim locator-less with the count named
in the review sidecar — never an arbitrary pick.

Two things to get right up front:

1. Inference deliberately reads pre-run, **mtime-stale** artifacts (that is where the
   numbers are), which does not weaken the freshness guard because an inferred
   locator is a *binding site*, not evidence, and only becomes a verdict when a fresh
   run rebinds it under the unchanged guard — state that honestly rather than
   papering over the apparent tension.
2. Keep the existing `load_claims` round-trip invariant so we never emit a draft our
   own reproduce path rejects.

Constraints: stdlib-only, no `models.py` change, no signature break, real fixture
repos in CI.

---

## Why this was picked (from `/contig-next`)

- It is the **last manual step** in the C8 paper → verdict chain. Everything on either
  side has shipped: paper-claim extraction + DOI/PDF intake
  (`docs/technical/CAPABILITY_ROADMAP.md:1762`) and all five locator families plus the
  freshness guard (`CAPABILITY_ROADMAP.md:2397`). Today a user runs `extract-claims`
  on a paper and must then hand-write a locator per claim before `contig reproduce`
  does anything.
- It is a **scope deferral, not a blocker**:
  `docs/planning/reproduce-paper-claims/prd.md:120` files it under "Nice-to-have
  (explicitly deferred, not this slice) — Locator **inference** … a separate, harder
  slice; v1 emits locator-less drafts by design", and `CHANGELOG.md:1635` confirms the
  shipped command emits "**No locator inference**".
- **Pure reuse of shipped primitives** — deep, not broad. Fully CI-observable with real
  fixture repos on disk (the slice-8 precedent, `CAPABILITY_ROADMAP.md:2250`), not
  injected-seam reasoning.
- Feeds the `reproduce-case-promote` corpus channel (`CAPABILITY_ROADMAP.md:2295`):
  claims that are currently *never attempted* start earning real verdicts.

## Known caveats carried in from the pick

- **Freshness-guard tension (apparent, not real).** The guard
  (`CAPABILITY_ROADMAP.md:2397`) makes any file whose mtime predates the run start
  UNVERIFIED and never parses it. Inference is a *pre-run search* over exactly those
  committed outputs. Resolution to state explicitly in the PRD: inference proposes a
  binding site, never evidence; the locator becomes a verdict only when a fresh run
  rebinds it under the **unchanged** guard.
- **False locators.** A value like `0.05` appears in dozens of places. Inherit slice
  4's ambiguity rule: 0 or >1 candidates → no locator, count named, never an
  arbitrary pick.

## Ranked against (for the record)

Beat: local `source_commit`/dirty-state capture (`CAPABILITY_ROADMAP.md:2270`),
RO-Crate reference-identity export (`:1245`), and the unmerged C9 Jev triage
capability (`origin/feat/jev-triage`, recommended for demotion — solves scale the
product does not have yet).

Rejected as **blocked**: bwa-mem2 index build+redirect —
`docs/planning/self-heal-bwa-mem2-index/understanding.md:18-30` (sarek auto-builds it;
iGenomes stages a classic `BWAIndex/`; no CLI flag can supply a broken one → no
reachable trigger).
