---
name: prd-interview
description: Conduct a collaborative product requirements interview between PM and engineering. Use when turning a brief or feature idea into a structured PRD and aspect-level specs through guided discovery and pressure-testing. Triggers on "prd interview", "requirements interview", "prd-interview".
tags:
  - documentation
  - planning
metadata:
  status: trial
---

# PRD Interview

Conduct a structured product requirements interview to turn a brief or feature idea into a complete PRD.
This is a collaborative exercise — the PM hat brings product context, the engineering hat brings technical reality.
Challenge assumptions. Pressure-test scope. Document what survives.

Do not create files until the Document phase.
If the tool supports a read-only or plan mode, switch to it now.

## Context

This skill is the first step in the brief-to-code pipeline (it's Phase 3 of `contig-begin-fast`).
Input is typically the gathered issue/brief dump at `docs/planning/_card/issue.md` plus the deep-dig understanding note.
Output is a structured PRD plus aspect-level specs that feed directly into `tech-plan`.

**Contig guardrail:** before documenting, sanity-check the work against `CLAUDE.md`. The moat is the run / debug / self-heal / verify / reproduce layer (Layer 2), **not** natural-language→workflow generation (Layer 1, which we consume). If the requirements drift toward building Layer 1 as the product, flag it in the interview, not after.

## Discover & Challenge

Read the user's input — the issue dump, brief, or pasted requirements.
Read key files (graphify-first per `CLAUDE.md`, then targeted reads under `src/contig/`) to understand current architecture.
Ask if the user is aware of prior art or similar internal/external solutions — offer to search if not.

Then pressure-test. Do not soften these. Frame as collaborative due diligence, not criticism.

- "What happens if we don't build this?"
- "Imagine this launched 6 months ago and failed. What went wrong?"
- "What are we choosing NOT to build if we build this?"

If the user has heard the challenge and wants to proceed, proceed.

Fill remaining gaps with focused questions, 2-3 at a time, grouped by topic:

- **Users & Problem**: Who has this problem? What's the cost of the status quo?
- **Success**: How will we measure it? Target numbers?
- **Scope**: What is explicitly out of scope?
- **Requirements**: Must-have vs. should-have vs. nice-to-have?
- **Technical Fit**: Stack constraints? Reproducibility/verification implications? Where does it sit in the orchestrate→run→verify pipeline?

Skip what you can infer.
Challenge vague answers — ask for examples, numbers, edge cases.
Flag technical pitfalls from the code you read — don't wait to be asked.

**Stop when** the problem is clear without guessing, success metrics are measurable, must-haves have testable criteria, out-of-scope is explicit, and major technical risks are identified.

## Confirm

Summarize: the problem, proposed approach, scope, success criteria, risks, and unresolved concerns.
If the challenge raised serious doubts, say so directly. The user decides, but with eyes open.
Ask the user to confirm before writing.
Confirm the feature slug for the directory name (e.g., `verify-layer`, `self-heal`). Do not name the slug `<type>-<id>` — the id lives in the branch/PR.

## Document

Omit sections that don't apply — do not write "Not applicable."

**Filename:** `prd.md`
**Location:** `docs/planning/{slug}/` — slug is the feature name confirmed during the Confirm phase.
Create the directory if needed. User can override location.
Examples: `docs/planning/verify-layer/prd.md`, `docs/planning/self-heal/prd.md`.

The feature directory is the workspace for all planning artifacts.
This skill can continue into aspect decomposition and create `spec.md` files.
`tech-plan` then creates implementation plans inside those aspect directories:

```
docs/planning/{slug}/
├── prd.md                        ← this skill's output
├── {aspect}/                     ← one directory per aspect
│   ├── spec.md                   ← this skill's decomposition output
│   ├── plan_YYYYMMDD.md          ← tech-plan output
│   └── ...                       ← team additions
└── ...                           ← research, design, ADRs, etc.
```

### PRD structure

- **Problem Statement**: What problem are we solving? For whom? Evidence it's real.
- **Goals & Success Metrics**: What does success look like? How will it be measured?
- **User Personas & Scenarios**: Who uses this and in what context? (Contig ICP: lone computational biologist, wet-lab scientist who can't code, core facilities, biotech.)
- **Requirements**: Core features and behaviors, prioritized as must-have, should-have, nice-to-have.
- **Technical Considerations**: Architecture fit, constraints, dependencies, integration points. Call out reproducibility and verification impact explicitly.
- **Risks & Open Questions**: Unresolved items, potential blockers, what could go wrong.
- **Out of Scope**: Explicitly excluded features or concerns.

Include when relevant: Data Model, Artifact/Run Contracts, Non-Functional Requirements.

After writing, surface open questions and unresolved risks.
Then offer to continue immediately into aspect decomposition (below).

## Aspect Decomposition Mode (same skill)

Use this mode after the PRD is confirmed, or when a user comes back later with an existing PRD and asks to break it down.

1. Propose aspect candidates (typically 2-8), each with a one-line boundary.
2. Confirm aspect names with the user (`kebab-case` directory names).
3. For each confirmed aspect, write or update `docs/planning/{slug}/{aspect}/spec.md`.
4. Keep each spec focused and buildable by one engineer (or agent) at a time.

Each `spec.md` should include:

- Problem slice and user outcome for this aspect
- In-scope requirements
- Out-of-scope boundaries
- Acceptance criteria (testable)
- Dependencies and sequencing notes
- Open questions or risks specific to this aspect

If the user only wants the PRD now, stop after `prd.md`.
`tech-plan` can pick up later and request aspect selection if specs are still missing.

## Edge Cases

- **Update existing PRD**: Read the file, ask what changed, update in place.
- **Existing PRD, no aspect specs yet**: Run Aspect Decomposition Mode without re-running full discovery.
- **User starts with prd-interview only (no prd-generator)**: Continue normally; this skill can produce both `prd.md` and aspect `spec.md` files.
- **User says "just write it"**: Write from what you have, but flag gaps in Open Questions and still include at least one challenge question.
- **Detailed spec already provided**: Review against structure, focus on the challenge phase, skip covered sections.
- **No brief exists**: Run full discovery from conversation. Note that the PRD is based on discussion rather than an artifact.
