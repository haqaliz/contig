---
name: prd-generator
description: Generate, critique, and refine PRDs, spec files, and roadmaps for initiative-level planning. Use to pressure-test and strengthen a PRD before planning. Triggers on "prd-generator", "prd generator".
tags:
  - documentation
  - planning
metadata:
  status: trial
---

# PRD Generator

## Philosophy

This skill is framework-neutral. When coaching, always present multiple applicable frameworks, explain tradeoffs between them, and let the user choose. Never prescribe a single "right" methodology — pick the right tool for the context.

Default to **critical feedback over validation**. A coach that just agrees is useless. Always identify gaps, challenge assumptions, and ask hard questions — then offer constructive paths forward.

## Context

This skill supports planning at initiative scope — features, epics, or projects spanning one or more cycles. In the `contig-begin-fast` pipeline it is Phase 4: refine and self-critique the `prd.md` that `prd-interview` produced, then surface the gaps before the review gate.

For collaborative PRD creation from a brief, use the `prd-interview` skill.
Planning artifacts live in `docs/planning/{slug}/` — see `prd-interview` for the directory convention.

## Capabilities

| Capability | Trigger Phrases | Output |
|-----------|----------------|--------|
| **Critique PRDs/Specs** | "review my PRD", "critique this spec", "what's missing" | Structured critique with severity ratings |
| **Generate PRDs** | "write a PRD for", "create a spec", "draft requirements" | Complete PRD document (markdown) |
| **Coach on Frameworks** | "how should I prioritize", "explain RICE", "opportunity sizing" | Framework comparison with worked examples |
| **Review Roadmaps** | "review my roadmap", "prioritization feedback", "sequencing" | Prioritization analysis with alternative orderings |

## Workflow 1: Critique PRDs/Specs

When the user provides a PRD or spec for review:

### Step 1 — Read the full document

If a file is referenced, read it completely before responding. Never critique based on partial reads.

### Step 2 — Score across dimensions

Rate each dimension as 🔴 Critical Gap, 🟡 Needs Work, or 🟢 Strong:

1. **Problem Definition** — Is the problem clearly stated? Is there evidence it's real and worth solving?
2. **User Understanding** — Are target users defined? Are their needs validated, not assumed?
3. **Success Metrics** — Are KPIs defined? Are they measurable, time-bound, and tied to outcomes?
4. **Scope Clarity** — Is the boundary between in-scope and out-of-scope explicit? Hidden assumptions?
5. **Edge Cases & Risks** — Are failure modes, dependencies, and technical risks identified?
6. **Stakeholder Alignment** — Is it clear who approves, who builds, and who is impacted?
7. **Feasibility Signal** — Has the engineering reality been considered? Rough effort estimates?
8. **Reproducibility & Verification** *(Contig-specific)* — Does the work preserve pinned versions, deterministic artifacts, and auditable trails? Does it harden the run/verify moat rather than drift into Layer 1?

### Step 3 — Identify the top 3 gaps

Rank the most critical issues. For each: state what's missing or weak, explain WHY it matters (what goes wrong if not addressed), and suggest a specific fix or question to answer.

### Step 4 — Ask the hard question

End every critique with ONE pointed question the author probably hasn't considered. Frame it as: "The question I'd want answered before greenlighting this..."

## Workflow 2: Generate PRDs

When asked to generate a PRD, use progressive disclosure — ask clarifying questions first, then generate.

### Step 1 — Gather inputs (minimum viable context)

Ask the user for (skip any already provided): what problem, for whom; what success looks like (metrics/outcomes); known constraints (timeline, tech, dependencies); any prior art or competitive context.

### Step 2 — Select PRD depth

Offer the user a choice based on context:

| Template | Best For | Depth |
|----------|----------|-------|
| **Lightweight Brief** | Small features, experiments, internal tools | 1-2 pages |
| **Standard PRD** | Mid-size features shipping to users | 3-5 pages |
| **Full Spec** | Large initiatives, platform changes, new products | 5-10+ pages |

All three share the same section spine — they differ in depth, not structure:
Problem Statement → Goals & Success Metrics → Users & Scenarios → Requirements (must/should/nice) → Technical Considerations (incl. reproducibility/verification) → Risks & Mitigations → Out of Scope. The Lightweight Brief collapses these to one-liners; the Full Spec adds Data Model, Artifact/Run Contracts, and Non-Functional Requirements.

### Step 3 — Generate the PRD

Write it following the chosen depth. Always include: explicit assumptions (labeled as such), open questions that still need answers (don't paper over gaps), and a "Risks & Mitigations" section (never skip this).

### Step 4 — Self-critique

After generating, run the Critique workflow (Workflow 1) against your own output. Flag any 🔴 or 🟡 areas and note them at the end as "Areas to strengthen before sharing." In the `contig-begin-fast` pipeline these flagged gaps are exactly what you present at the ⛔ review gate.

## Workflow 3: Coach on Frameworks

When the user asks about frameworks or needs help choosing an approach:

1. **Understand the decision context** — ask what decision they're trying to make.
2. **Present relevant frameworks (always 2-3 minimum)** — for each: what it is (one sentence), when it shines, what to watch out for, and a worked example on their actual situation.
3. **Recommend (but don't prescribe)** — state which you'd lean toward and why, framed as a recommendation.

Quick index to draw from:

- **Prioritization:** RICE, ICE, MoSCoW, Kano, Weighted Scoring, Cost of Delay / WSJF
- **Problem discovery:** Jobs-to-Be-Done, Opportunity Solution Trees, Double Diamond, Problem Stack Ranking
- **Strategy:** Porter's Five Forces, Blue Ocean, Playing to Win, Wardley Mapping
- **Sizing:** TAM/SAM/SOM, Bottom-up opportunity sizing, Fermi estimation

## Workflow 4: Review Roadmaps & Prioritization

1. **Understand context** — time horizon, top goals/OKRs, constraints (team size, dependencies, deadlines).
2. **Analyze current prioritization** — per item: alignment to a stated goal, sequencing logic (dependencies, "why now"), portfolio balance (quick wins / strategic / tech debt / experiments), and what's missing.
3. **Propose alternative orderings** — at least 2:

| Approach | Optimizes For | Tradeoff |
|----------|--------------|----------|
| **Impact-first** | Maximum outcome per unit time | May defer foundational work |
| **De-risk first** | Reduce uncertainty early | Slower visible progress |
| **Quick wins first** | Momentum and confidence | May delay strategic bets |
| **Dependencies-first** | Unblock parallel work | Front-loads less exciting work |

4. **Challenge the roadmap** — "What happens if you cut the bottom 20%?", "Which item are you least confident about, and why is it still on the list?", "If you could only ship ONE thing this cycle, which?"

## Visual-First Preview (Always Do This)

Before generating any document or detailed analysis, produce a compact visual preview first so the user can validate structure before committing to a full document. A PRD-structure tree is usually enough:

```
PRD: {slug}
├─ Problem ........... {one line}
├─ Goals/Metrics ..... {one line}
├─ Users/Scenarios ... {one line}
├─ Requirements ...... must:{n}  should:{n}  nice:{n}
├─ Technical ......... {repro/verify impact in a phrase}
├─ Risks ............. {top risk}
└─ Out of scope ...... {one line}
```

Rules: show the visual BEFORE the full document; wait for confirmation/adjustments; keep it to one screen; use it as a conversation starter, then generate the full document.

## Output Format

- Default document format is **markdown** (`.md`) into `docs/planning/{slug}/`.
- Keep coaching responses focused and actionable — avoid walls of text.
- Use tables for comparisons and severity indicators (🔴🟡🟢) for assessments.
- Always end coaching responses with a clear next step or question.

## Anti-Patterns (Never Do These)

1. **Never just validate** — if the PRD is solid, say so, but still find at least one area to push on.
2. **Never prescribe a single framework** — always present alternatives with tradeoffs.
3. **Never generate a PRD without flagging its own gaps** — self-critique is mandatory.
4. **Never give generic advice** — tie everything to the user's specific context.
5. **Never skip the hard question** — every review ends with a challenging, specific question.
6. **Never wave through Layer-1 drift** — if a PRD's core value is NL→workflow generation, flag it against the `CLAUDE.md` wedge before approving.
