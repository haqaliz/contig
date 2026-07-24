# Card: feat reproduce-paper-claims (C8, next slice — paper-claim extraction)

**Type:** feat · **Owner:** aliz · **Branch:** `feat/reproduce-paper-claims/aliz`

No GitHub issue — this unit of work came from `/contig-next` (cn), 2026-07-24. The
recommendation below is the source brief.

## Brief

Turn `contig reproduce` from "point it at a repo **and hand-author a claims file**" into
"point it at the paper's text and get a *draft* claims file to review" — extracting the
paper's stated numeric claims (value + tolerance + a candidate locator) behind an
injectable seam, gated by human review before any binding.

Slices 1–7 (v0.40.0 → v0.48.0) built the whole reproduce spine: the per-claim verdict
(`REPRODUCED`/`WITHIN-TOLERANCE`/`DIVERGED`/`UNVERIFIED`), the JSON/TSV-CSV/stdout/notebook
locators, environment resurrection, the mtime freshness guard, remote `https://` intake,
and `--rev` revision pinning. The value the user still hand-supplies is the **claims list
itself** (`CHANGELOG.md:697` — the repo writes `results.json`, the user writes the claims
file). Paper-claim extraction is the step named as "next"/deferred in **every** C8 slice
deferral list (`CAPABILITY_ROADMAP.md:1073`; `CHANGELOG.md:420,523,595,686`).

## Why it's the pick (moat)

- Squarely **Layer 2** — this is verification *input* (extracting claims to verify), not
  Layer-1 workflow authoring (`CLAUDE.md` wedge). It deepens the reproduce moat: the
  reproduce PRD's own review gate called externally-credible reproduce the point of C8,
  and claim extraction is what makes it turnkey on a real published paper.
- "Gets better as base models improve" (`CLAUDE.md` #3) — the extractor is an env-gated,
  injectable seam, exactly like the optional `llm` detector already shipped
  (`FEATURES.md:225`).
- The **verdict contract already contains the risk**: any claim that can't be bound or is
  ambiguous degrades to `UNVERIFIED`, never a false `REPRODUCED` — the invariant every C8
  slice holds. Extraction can be imperfect without ever lying.

## Key design risk (resolve first in the dig)

**Reliable claim extraction from prose is the unresolved feasibility question** — this is
why it stayed deferred through 7 slices. The honest first slice is narrow:

- Extract **candidate** numeric claims from a supplied **plain-text / markdown** source
  (NOT PDF, NOT DOI — those stay out of scope: network + parsing) into a **draft claims
  file the user edits**, never auto-verifying unreviewed claims.
- Keep the extractor an **injectable seam** — a regex/heuristic core that always runs, plus
  an **optional** env-gated LLM assist that is **never run in CI** (deterministic
  fixtures, mirroring the whole C8 track's "no LLM/network/pip in CI" discipline).
- Extraction feeds a **human-review gate**: the output is a *draft* claims file (the same
  schema `load_claims` already validates), not a set of auto-bound claims.
- **Figures stay hard-blocked** (no plot-hash, stdlib-only). Table-image claims blocked.

## Verification caveat

As with every C8 slice: **no real LLM, network, or PDF in CI.** The extractor seam is
injected; the real optional-LLM path is asserted for prompt/shape only and never executed.
Correctness of the deterministic (regex/heuristic) core is unit-tested against on-disk
fixture text/markdown; the LLM assist is manual-gate only.

## Scope boundaries (explicit non-goals for this slice)

- No PDF parsing, no DOI resolution, no paper *fetching* (all deferred/out of scope).
- No auto-verification of unreviewed claims — extraction produces a draft for review.
- No figure/plot or table-image claims (hard-blocked, no plot-hash).
- No change to the shipped verdict/locator/bundle contract — this is claims-file *input*
  generation, feeding the unchanged `load_claims` → `run_reproduction` path.

## No PRD yet

There is no `docs/planning/reproduce-paper-*` dir on master — scope this from the C8
deferral lists test-first. The candidate is well-supported by the docs (named repeatedly),
just not yet PRD'd.
