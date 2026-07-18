# Card: feat/reproduce-output-locator (C8 slice 1.5)

**Type:** feat · **Slug/id:** reproduce-output-locator · **Owner:** aliz
**Branch:** feat/reproduce-output-locator/aliz
**Source:** no GitHub issue — inline brief from the `/contig-next` handoff (2026-07-18).
Capability **C8** in `docs/technical/CAPABILITY_ROADMAP.md:1047-1082`; explicitly the
**slice 1.5** deferred by the v0.40.0 walking skeleton.

---

## Brief

Build **C8 slice 1.5 — a claim-level output-locator for `contig reproduce`**, the next slice
after the v0.40.0 walking skeleton (shipped today). It is the piece the reproduce PRD
(`docs/planning/reproduce-published-work/prd.md:190-215`) names as what makes reproduce
**"externally credible."**

Generalize the skeleton's value-binding (slice-1 M4) so each claim can point at **where its
number lives in the repo's own outputs** — e.g.
`{"from": "out/summary.json", "path": "$.coverage.mean"}` — instead of requiring the repo to
hand-write a Contig-shaped flat `results.json` keyed by claim id. This turns `contig reproduce`
from a fixtures-only / cooperative-repo demo into something that reads numbers out of **real,
unmodified cloned repos**.

Reuse the shipped core in `src/contig/verification/reproduce.py` unchanged: `classify` /
`reduce_reproduction` / `ClaimResult` / `ReproduceRecord`. Only the **value-binding** step
generalizes.

## Per-claim verdict vocabulary (unchanged from slice 1)

`REPRODUCED` / `WITHIN-TOLERANCE` / `DIVERGED` / `UNVERIFIED`.

## Honesty contract (non-negotiable)

- An unresolvable locator, a missing file, or a non-numeric / non-finite (`NaN`/`inf`) value
  is `UNVERIFIED` — never a false pass, never `DIVERGED`.
- Reports whether the *computation* reproduces the stated numbers — never a judgement on the
  paper's *conclusions*.
- No raw-data egress — only hashes + claim diffs leave the box.
- **Stdlib-only** — JSON/TSV path expressions; no image/plot hashing, no new runtime deps
  (`pydantic`/`typer`/`cryptography` only, `pyproject.toml`).
- **Deterministic CI** — no real repo, no network; canned fixture outputs exactly like slice 1.

## Known caveat (dig into this first)

An output-locator makes reproduce work on repos that emit **structured** outputs (JSON/TSV).
Many real repos still print numbers to stdout, bury them in CSVs/plots, or only produce them
inside a notebook — those keep degrading to `UNVERIFIED` until slice 2 (env-resurrection) and
paper-parsing land. So: scope the locator to structured-file path expressions in this slice;
do not scrape stdout or parse prose. Figures stay hard-blocked (no plot-hash, stdlib-only).

## Why this was picked (from `/contig-next`)

- **Freshest capability, depth-first, unblocked.** Slice 1 shipped today (v0.40.0,
  `CHANGELOG.md:9-58`). The locator reuses the shipped `classify`/`reduce_reproduction`/
  `ClaimResult` core untouched; only value-binding generalizes. No new dependency.
- **The PRD's own greenlight question hangs on it.** `reproduce-published-work/prd.md:190-215`
  flags that slice 1 only reproduces *cooperative* repos (those that emit a Contig-shaped
  `results.json`), so most real uncooperative repos degrade to `UNVERIFIED`; the output-locator
  is the "read numbers out of repos as they already are" answer, "interview option C".
- **On-moat.** Widens what we can verify + feeds the corpus; serves C8's viral-GTM thesis
  (`CAPABILITY_ROADMAP.md:1084-1096`). Inside every guardrail (`CLAUDE.md` #1-4).

## Guardrails (must hold) — `CLAUDE.md`, `CAPABILITY_ROADMAP.md:1149-1160`

- **Layer 2 only.** Verify-and-reproduce; never NL→workflow authoring; never a conclusions verdict.
- **Founder's edge / stdlib-only.** Pure-Python path resolution + scalar math, no new deps.
- **No raw-data egress.** Only hashes + claim diffs leave the machine.
- **Test-first.** Synthetic repo-output fixtures, no network, no real nf-core in CI.

## Relationship to prior/next slices

- Slice 1 (walking skeleton) = v0.40.0 (`CHANGELOG.md:9-58`,
  `CAPABILITY_ROADMAP.md:1047-1082`). Parent PRD: `docs/planning/reproduce-published-work/prd.md`.
- **This = slice 1.5** — the output-locator, explicitly deferred there.
- Slice 2 = environment resurrection (`ModuleNotFoundError` → install → retry, reusing C2),
  mapped in the slice-1 `understanding.md`. Remains the next-next slice; keep this slice from
  boxing it out but do not build it here.
