# Contig: Project Context for Claude Code

This file orients a coding agent working in this repository. Read it first. Deeper context lives in the `docs/` folder.

---

## What this project is

**Contig** is an **agentic bioinformatics analyst**. It ingests a researcher's raw sequencing data, selects and runs the right pipeline on their compute, debugs and self-heals failures, and returns a **verified, reproducible** result.

The name: a *contig* is one contiguous sequence assembled from many overlapping fragments. The product assembles messy data, scattered tools, and broken steps into one verified working result.

Status: **pre-MVP, validation phase.** Expect docs and design ahead of code.

---

## The wedge (read this before proposing any feature)

There are two layers. Know which one you are touching.

- **Layer 1: natural language → workflow/script.** CROWDED and commoditizing (Galaxy, KNIME, BioMaster, BioWorkflow, general LLMs). **We do NOT build this as a product.** We consume it.
- **Layer 2: run it, debug it, self-heal failures, verify the output, guarantee reproducibility, end-to-end on the user's data and compute.** Essentially UNSOLVED. **This IS the company.**

Frontier models hit only ~17% on real bioinformatics analysis (BixBench, arxiv 2503.00096). The hard execution/verification layer is the moat.

---

## Key strategic constraints (do not violate)

1. **Do not build Layer 1.** If a task drifts toward "make Contig generate workflows from English" as the core value, stop and flag it. That capability is a dependency we consume, not the product.
2. **The moat is execution / verification / reproducibility infrastructure + accumulated workflow-evaluation data, NOT prompting.** Favor work that hardens the run-and-verify harness and captures evaluation data over work that tweaks prompts.
3. **Build the part that gets BETTER as foundation models improve.** A better base model should make our orchestrator better, never make our product redundant.
4. **Stay inside the founder's edge.** No work that requires wet-lab/clinical credentials, proprietary biological datasets, or heavy regulatory/EHR integration as a precondition. Those alternatives were deliberately rejected (see VISION.md → "Why not the alternatives").

---

## Tech direction

- **Agentic system**: an orchestrator that plans, runs real pipelines, isolates/diagnoses failures, self-heals, and verifies outputs. Treat failure recovery and verification as first-class, not afterthoughts.
- **Full-stack + ML**: product UI/API + the ML/agent layer + evaluation machinery. Exact stack is TBD during validation; check `docs/technical/ARCHITECTURE.md` before assuming.
- Pipelines run on the **user's data and compute**; reproducibility (pinned versions, deterministic artifacts, auditable trails) is a core requirement, not a nice-to-have.
- Capture run telemetry (failures, fixes, verified outputs) wherever feasible: it feeds the compounding evaluation dataset that is part of the moat.

---

## Founder profile

Solo / small-team. **Full-stack developer + ML engineer + genetics passion.** No wet-lab or clinical credentials, and that is by design: the moat is engineering, which is the founder's strength. Optimize for an engineering-defensible product.

---

## Folder / docs structure

```
README.md                          # Repo front door
VISION.md                          # Narrative thesis, moat, non-goals
CLAUDE.md                          # This file
docs/
  RESEARCH_FINDINGS.md             # Validated evidence base
  ROADMAP.md                       # Phased plan
  product/PRODUCT_SPEC.md          # Product surface and flows
  technical/ARCHITECTURE.md        # Agentic execution/verification design
  business/MARKET_ANALYSIS.md      # Market, competitors, positioning
  business/BUSINESS_MODEL.md       # Revenue, pricing, ICP
  business/GTM.md                  # Go-to-market
```

Some docs may be placeholders during validation. **Detailed context lives in `docs/`.** Consult the relevant file before making non-trivial decisions, and keep docs in sync when you change direction.

---

## Quick facts for grounding (do not fabricate beyond these)

- ~74% of wet-lab scientists have no programming experience (arxiv 2507.20122v1).
- Building end-to-end pipelines needs rare dual genomics+computation expertise (arxiv 2507.20122v1; nature s41598-025-25919-z).
- LLMs already generate accurate Galaxy/Nextflow workflows from NL; small models + RAG reach expert level on the conceptual layer.
- Frontier models reach only ~17% on real bioinformatics analysis (BixBench, arxiv 2503.00096).
- Business model: per-seat SaaS ($50-200/mo individual; team/lab plans) + usage on managed compute. ICP: lone computational biologist, wet-lab scientist who can't code, core facilities, biotech.

If you need a statistic that isn't here, do not invent one; say it's unverified.
