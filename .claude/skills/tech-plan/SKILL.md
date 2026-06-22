---
name: tech-plan
description: Create a phased technical implementation plan from planning artifacts in docs/planning (PRD + aspect spec). Use after prd-interview when ready to execute a specific aspect. Triggers on "tech plan", "implementation plan", "plan from PRD".
tags:
  - planning
  - documentation
metadata:
  status: trial
---

Create a phased technical implementation plan from planning artifacts under `docs/planning/{slug}/`.
Inputs can come directly from `prd-interview`; do not require `prd-generator`.
This is Phase 5 of `contig-begin-fast` — the plan it produces is executed in Phase 6 through the agents team under strict TDD.

If the user provided artifacts in context (attached file, pasted content, or referenced path), use them directly.
Otherwise, search the workspace for:

- PRDs matching `docs/planning/*/prd.md`
- Aspect specs matching `docs/planning/*/*/spec.md`

Analyze the current codebase (graphify-first per `CLAUDE.md`, then targeted reads under `src/contig/` and `dashboard/`), then create a detailed **Implementation Plan** optimized for autonomous agent execution.
The plan should be structured so the agent team can work through it systematically with minimal human intervention.

## Handoff Contract

- **Feature requirements source:** `docs/planning/{slug}/prd.md`
- **Aspect requirements source (preferred):** `docs/planning/{slug}/{aspect}/spec.md`
- **Plan output (required):** `docs/planning/{slug}/{aspect}/plan_YYYYMMDD.md`

Plan one aspect at a time. If a feature has multiple aspects, create one plan file per aspect.

**Filename:** `plan_YYYYMMDD.md` (YYYYMMDD is today's date, e.g., `plan_20260622.md`)
**Location:** the aspect directory (e.g., `docs/planning/verify-layer/output-check/plan_20260622.md`). Create it if needed.
If the user provided an aspect spec from a different location, write the plan alongside that spec.
If only a PRD is provided (no aspect spec), ask which aspect to plan, create or update `spec.md` for that aspect, then write the plan in that aspect directory.
If the PRD was pasted or attached (no file path), ask the user to confirm both feature slug and aspect name, then write to `docs/planning/{slug}/{aspect}/plan_YYYYMMDD.md`.

## Deliverables

### 1. Project Setup Checklist

- Directory/module structure to create (under `src/contig/`, `tests/`, or `dashboard/`)
- Configuration needed (pyproject entries, env, pinned tool versions for reproducibility)
- Dependencies to add (with specific versions where critical) — Python via `uv add`, dashboard via `npm install`

### 2. Implementation Phases

Break the build into sequential phases that can be executed autonomously. For each phase:

**Phase N: [Name]**

- **Goal:** What this phase accomplishes
- **Prerequisites:** What must exist before starting
- **Files to create/modify:** Explicit list
- **Implementation steps:** Numbered, specific instructions
- **Validation:** How to verify the phase is complete (`uv run pytest <path>`, expected outputs; `npm test` / `npm run build` for dashboard)
- **Commit message:** Suggested commit message for this phase

Each phase is a unit the agents team can own end-to-end under TDD (RED → GREEN → REFACTOR).

### 3. File-by-File Build Order

Ordered list of every file to create, with: filepath, one-line purpose, key functions/components it exports, and dependencies on other files.

### 4. Testing Strategy

- Unit tests to write (mapped to implementation phases) — these are written **first** in Phase 6
- Integration tests
- Manual verification steps
- Test commands: `uv run pytest` (Python core), dashboard test/build commands for UI

### 5. Environment & Reproducibility

- Environment variables needed
- External tools/services to configure (and how they're pinned)
- Local setup: `uv sync`; dashboard `npm install`
- Note any determinism/auditability requirements — Contig treats reproducibility as a core requirement, not a nice-to-have

### 6. Edge Cases & Error Handling

- Known edge cases to handle
- Error states to account for (and how failures are surfaced/self-healed, given Contig's run/verify focus)
- Fallback behaviors

### 7. Agent Execution Notes

- Suggested checkpoints for human review
- Areas likely to need iteration or debugging
- Sections where the agent should ask for clarification before proceeding

## Guidelines

- Be extremely explicit — assume no implicit knowledge
- Prefer small, testable increments over large monolithic steps
- Each phase should result in runnable (even if incomplete) code, with the suite kept green
- Flag any spec ambiguities that could block implementation
- Note assumptions clearly
- Optimize for autonomous execution by the agents team with minimal back-and-forth
- Don't plan work that builds Layer 1 (NL→workflow) as the product — flag it against the `CLAUDE.md` wedge instead

## Edge Cases

- **Greenfield vs. existing codebase**: For greenfield, include full setup. For existing code, skip scaffolding and focus on integration points and impact analysis.
- **No aspect spec exists yet**: Derive a candidate aspect list from the PRD, ask the user to choose one, draft `spec.md`, confirm, then plan.
- **Incomplete PRD**: If the PRD lacks testable acceptance criteria or measurable metrics, flag this and recommend running `prd-interview` before planning.
- **Multiple PRDs**: Separate plans per PRD unless they share infrastructure, in which case note shared phases.
- **Multiple planning sessions**: If an aspect has multiple `plan_YYYYMMDD.md` files, base the new plan on the current `prd.md` + `spec.md`. Create a new plan file with today's date.
- **PRD with flagged gaps**: If `prd-interview` produced the PRD via the "just write it" path, gaps may be marked. Note these in the plan and recommend resolution before the affected phase.
