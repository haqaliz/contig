# Card: feat/reproduce-published-work

**Type:** feat
**Slug/id:** reproduce-published-work
**Owner:** aliz
**Branch:** feat/reproduce-published-work/aliz
**Source:** No GitHub issue — inline brief (from the `/contig-next` handoff). Capability **C8** in `docs/technical/CAPABILITY_ROADMAP.md`.

---

## Brief

Start capability **C8 — Reproduce & verify *existing published* work** (`docs/technical/CAPABILITY_ROADMAP.md:1047-1097`). Turn the shipped run → self-heal → verify → reproduce engine around to face *third-party published* analyses, ending in a signed, re-runnable per-claim verdict — the same Layer-2 engine pointed at *other people's* published code+data.

**Scope this FIRST slice narrowly:**
- A `contig reproduce <local repo>` CLI skeleton that runs a repo's script.
- An **environment-resurrection** step that traces the real execution and self-heals `ModuleNotFoundError` / `ImportError` by installing missing deps — **reusing C2's self-heal / pin machinery, not rebuilding it**.
- Take an **explicit claims file** for now (defer paper-parsing).
- Defer the full claim-to-artifact semantic diff to later slices (a minimal per-claim compare may be in scope — settle in the interview).

**Honesty contract (non-negotiable):**
- `UNVERIFIED` is never rendered as reproduced.
- It reports whether the *computation* reproduces the stated numbers — never a judgement on the paper's *conclusions*.
- No raw-data egress — runs on the user's / CI compute; only hashes and claim diffs leave the box.

**Per-claim verdict vocabulary (from the roadmap):** `REPRODUCED` / `WITHIN-TOLERANCE` / `DIVERGED` / `UNVERIFIED`.

---

## Why this was picked (from `/contig-next`)

- **Next genuinely unblocked frontier.** C5's mismatch-detector next slice is largely blocked (no sample-side contig signal in raw FASTQ, per `CAPABILITY_ROADMAP.md:333`) and overlaps shipped C2 harmonization. C6's fold-in and C7's M5 eval fold-in are both blocked pending a labeling design for unlabeled C1/C3 signals (`:879, :1028`). With C1–C7 hardened through v0.39.0, C8 is the next big on-thesis move.
- **Highest moat leverage.** "The strongest quantified pain of the whole verification thesis": ~3.2% of 27,271 biomedical notebooks reproduce (`:1056-1061`); a new publicly-sourced corpus stream feeding C6; a free viral acquisition channel (Principle #5). Gets better as base models improve (claim-extraction + env-resurrection) — CLAUDE.md #2/#3.
- **Reuses shipped machinery depth-first.** Env resurrection "reuses and extends C2's self-heal and the container/pin machinery" (`:1071`); claim diffing reuses existing float-tolerance / plot-hash diffing.

## Guardrails (must hold) — `CAPABILITY_ROADMAP.md:1095-1097`, `CLAUDE.md`

- **Layer 2 only.** Verify-and-reproduce; never author pipelines from English. Never a scientific judgement on the paper's conclusions.
- **Founder's edge.** Pure engineering (env resurrection, claim diffing). No wet-lab / clinical / proprietary data.
- **No raw-data egress.** Only hashes and claim diffs leave the machine.
- **Test-first.** Synthetic repo fixtures, no network, no real nf-core in CI.

## Known caveats (from the handoff, to resolve in the dig / interview)

- C8 is marked **proposed · M7+** and has **no `docs/planning/` dir yet** — this pick rests on the ~50-line C8 section of the roadmap (authoritative intent, but no aspect breakdown exists).
- **Environment resurrection is the genuinely hard, open-ended piece** ("the load-bearing piece"). Real feasibility risk → keep the first slice narrow, test-first against a synthetic repo, no network.

## Roadmap-stated C8 build surface (for reference — later slices, not all this slice)

1. **Environment resurrection (load-bearing):** reconstruct a runnable env for an *uncooperative* repo from a **traced real execution** (observed imports / loaded versions), not a trusted manifest — ModuleNotFoundError/ImportError + dependency installs are ~76% of reproduction failures. Reuses/extends C2 self-heal + container/pin machinery.
2. **Claim-to-artifact alignment:** parse the paper (or a claims file) for numeric claims — a reported statistic, a table cell, a figure — and semantically diff each against the regenerated artifact with existing float-tolerance / plot-hash / seed-aware diffing.
3. **Per-claim verdict** (`REPRODUCED` / `WITHIN-TOLERANCE` / `DIVERGED` / `UNVERIFIED`) + a signed, re-runnable bundle — same honesty contract as every verdict.
4. **`contig reproduce <repo|doi>`** surface (CLI + dashboard card), community-facing and free.

**Acceptance (roadmap):** a synthetic repo whose script regenerates a known figure/number yields `REPRODUCED` per claim; a deliberately drifted dependency or altered constant yields `DIVERGED` with the exact claim and observed-vs-stated values named; a repo with an unresolvable environment yields `UNVERIFIED`, never a false reproduce. Deterministic, no network.

**Dependencies:** C2 (self-heal / environment repair), C5 (input-data integrity), C6 (eval flywheel), and the shipped reproduce bundle.
