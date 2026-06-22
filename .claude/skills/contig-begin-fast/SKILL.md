---
name: contig-begin-fast
description: Use when starting work on a Contig unit of work (a GitHub issue id or an inline brief) and you want the fast path straight to an implementation plan. Triggers on "contig-begin-fast", "cbf", "cbf bug 12", "cbf feat verify-layer", "begin fast".
arguments: "type id"
---

# Contig Begin (Fast Track)

## Overview

Turn a single unit of work into shipped, test-driven code. The fast track is: **isolate → gather → dig → PRD → plan → implement (TDD).** No proposal/diagram deliverables (use `contig-begin` / `cb` when you need those).

**Two non-negotiables for this whole pipeline:**
- **Always work through the agents team.** Every phase with independent units of work is dispatched to agents and synthesized — never done serially in the main thread. See *Agents team (mandatory)*.
- **Implementation is always test-first**, via `superpowers:test-driven-development`, and is itself executed by the agents team. See Phase 6.

**Invocation:** `cbf <type> <id>` — e.g. `cbf bug 12`, `cbf feat verify-layer`, `cbf chore pin-nextflow`.

- `type` ∈ `bug | feat | feature | task | chore` (normalize `feature` → `feat`).
- `id` = a **GitHub issue number** when one exists, otherwise a short descriptive **slug** for the work.
- Owner is `aliz`.

## Task source: GitHub issue, tolerate absence

Contig's tracker is GitHub Issues, but the repo/issues may not be reachable (`gh` unauthenticated, Issues disabled, or the work was never filed). The pipeline degrades gracefully:

- If `id` is numeric and `gh issue view <id>` succeeds → use it as the source (Phase 1).
- Otherwise → ask the user for a one-paragraph **inline brief** and treat that as the source. Skip the `gh` fetch; everything else is identical.

## Pipeline

Run phases in order. **Do not skip the review gate.** Every phase runs through the agents team, and Phase 6 is strict TDD — never do parallelizable work or implementation serially in the main thread.

### Phase 0 — Isolate in a worktree

**REQUIRED SUB-SKILL:** Use `contig-worktrees`.

- Branch name: `<type>/<id>/aliz` (e.g. `bug/12/aliz`, `feat/verify-layer/aliz`).
- Worktree dir: `.claude/worktrees/<type>-<id>` (e.g. `.claude/worktrees/bug-12`).
- Create from `origin/master`. Contig has no `.worktreeinclude` files to copy today; run `uv sync` in the worktree before working.
- All subsequent work (context dump, PRD, plan) happens **inside this worktree.**

### Phase 1 — Gather context (`gh`, or inline brief)

Pull what's available and save a raw dump to `docs/planning/_card/issue.md` in the worktree so later phases (and the PRD) have a single source. (Filename is id-free on purpose — the id lives in the branch/PR; the worktree is already dedicated to one unit of work.)

Gather: the issue body, labels, linked/related issues and PRs, and **comments**. If there's no reachable issue, write the user's inline brief into the same file under a "Brief" heading.

**Commands and parsing:** see `references/gather-context.md`.

### Phase 2 — Deep dig

Before any PRD work, understand the real problem and the code it touches.

- Read the saved dump.
- Map the relevant code paths. **Contig has a `graphify-out/` graph — query it first** (`graphify query "..."`, `graphify explain "X"`) per CLAUDE.md, then read the files it points to. Relevant areas usually live under `src/contig/` (CLI in `contig.cli`, the orchestrator/agent layer, detector, verification) and `dashboard/` for UI work.
- Produce a short written "understanding" note: what the work is really asking, affected areas, ambiguities, and open questions.
- Surface contradictions between the issue/brief and the code — flag them, don't paper over them.
- Honor the strategic constraints in `CLAUDE.md` (the moat is the run/verify/reproduce layer, **not** Layer 1 workflow generation). If the work drifts into building Layer 1 as the product, flag it before planning.

### Phase 3 — Requirements interview

**REQUIRED SUB-SKILL:** Use `prd-interview`.

- Feed it the Phase 1 dump + Phase 2 understanding as the product brief.
- Answer from the gathered context where you can; ask the user only what the context can't resolve.
- Confirm a **descriptive** feature slug (kebab-case, e.g. `verify-layer`) for `docs/planning/{slug}/`. Do **not** name the slug `<type>-<id>` — the id lives in the branch and PR, not in committed doc paths.
- Output: `docs/planning/{slug}/prd.md` (+ aspect `spec.md` files if decomposed).

### Phase 4 — Generate & self-critique the PRD

**REQUIRED SUB-SKILL:** Use `prd-generator`.

- Refine `prd.md`, run its self-critique, and surface the 🔴/🟡 gaps.

### ⛔ Review gate — STOP

Present the PRD and its flagged gaps. **Wait for the user's explicit approval** before planning. Do not auto-advance to tech-plan.

### Phase 5 — Implementation plan

**REQUIRED SUB-SKILL:** Use `tech-plan`.

- Plan one aspect at a time from `prd.md` (+ `spec.md`).
- Output: `docs/planning/{slug}/{aspect}/plan_YYYYMMDD.md`.

### Phase 6 — Implement (TDD, agents team)

Start only after the plan is approved. Implementation is **always test-first** and **always run through the agents team** — never hand-written serially in the main thread.

**REQUIRED SUB-SKILL:** Use `superpowers:test-driven-development` — strict RED → GREEN → REFACTOR; no production code before a failing test.
**REQUIRED SUB-SKILL:** Use `superpowers:subagent-driven-development` to execute the plan — dispatch one agent per independent task from `plan_YYYYMMDD.md`; parallelize independent tasks with `superpowers:dispatching-parallel-agents`.

- Each dispatched agent owns one task and follows the TDD cycle inside it: write the failing test, make it pass, refactor.
- Run the suite after each task and keep the branch green: `uv run pytest` for the Python core; `npm test` / `npm run build` in `dashboard/` for UI work.
- Commit per task on the `<type>/<id>/aliz` branch (id lives in the commit/PR, never in code).
- You stay the integrator: sequence dependent tasks, synthesize agent results, and surface blockers at each checkpoint.

## Artifact layout (inside the worktree)

```
docs/planning/
├── _card/issue.md                 ← gh dump or inline brief (Phase 1)
├── {slug}/prd.md                  ← prd-interview / prd-generator
└── {slug}/{aspect}/plan_*.md      ← tech-plan
```

Phase 6 produces **code commits** on the `<type>/<id>/aliz` branch — not documents.

## Agents team (mandatory)

This pipeline is **always** run through a team of agents, never serially in the main thread. For each phase, dispatch agents for the independent units of work and synthesize their results yourself.

**REQUIRED SUB-SKILL:** Use `superpowers:dispatching-parallel-agents` for independent work, and `superpowers:subagent-driven-development` for executing plan tasks in Phase 6.

- **Phase 1–2:** one agent per related issue/PR (5-line summary + relevance) + one agent to map the affected code area (graphify-first). Keep the `gh` calls themselves batched in a single message.
- **Phase 6:** one agent per independent plan task; each agent works in strict TDD.

Gates, user-facing summaries, and integration stay with you — the agents do the fan-out work.

## Common mistakes

| Mistake | Fix |
|---|---|
| Working in the primary checkout | Always create the Phase 0 worktree first |
| Slug = `bug-12` | Use a descriptive slug; the id stays in branch/PR |
| Treating a `gh` failure as fatal | Fall back to an inline brief, keep going |
| Skipping the review gate | PRD must be approved before tech-plan |
| Building Layer 1 (NL → workflow) as the product | Stop and flag — that's a dependency we consume, not the moat |
| Inventing requirements the issue doesn't support | Flag as open question in the PRD instead |
| Implementing serially in the main thread | Execute the plan through the agents team (subagent-driven-development) |
| Writing code before a failing test | Implementation is strict TDD — RED before GREEN, always |
