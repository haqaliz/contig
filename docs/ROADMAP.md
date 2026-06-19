# Contig — Product Roadmap

> **Contig** is an agentic bioinformatics analyst. It ingests raw sequencing data, runs the right pipeline on the user's own compute, debugs and self-heals when steps fail, and returns a **verified, reproducible** result.

---

## Why this roadmap looks the way it does

**The wedge.** Layer 1 (natural language → script) is crowded and commoditizing — we avoid it. Layer 2 — actually *running* the pipeline end-to-end, debugging it, self-healing the failures, verifying the output, and making the whole thing reproducible — is unsolved. That is the company.

**The evidence we're building on:**
- The problem is real with high confidence. Roughly **74% of wet-lab scientists can't program**, and practitioners routinely scavenge solutions from Biostars threads and paper "Methods" sections rather than building robust pipelines [arxiv.org/html/2507.20122v1; nature.com/articles/s41598-025-25919-z].
- Current AI systems **fail on medium/complex analysis** — roughly **17% accuracy on real analytical tasks** on the BixBench benchmark [arxiv.org/abs/2503.00096]. Generation is easy; *getting a correct, runnable result* is the hard, valuable part.

---

## Guiding Principles

1. **Validate willingness-to-pay BEFORE scaling.** No platform, no breadth, no fundraising narrative until real bioinformaticians reach for a credit card. The single most important artifact of the next 90 days is a yes/no answer to "would you pay, how much, out of whose budget?"
2. **Narrow, then expand.** One pipeline, run flawlessly and self-healing, beats ten pipelines that mostly work. Depth is the moat; breadth is a later optimization.
3. **Verification is the product, not a feature.** Anyone can generate a script. We win by *proving the result is correct and reproducible.* Every phase must strengthen the verify/reproduce layer.
4. **Run on the user's compute.** Their data, their cluster/cloud, their control. This sidesteps data-governance objections that would otherwise stall every biotech conversation.
5. **Earn trust in the community before selling to it.** Biostars/r/bioinformatics/nf-core reputation is the cheapest, most durable acquisition channel we have.

---

## Phase Overview

| Phase | Theme | Duration | Exit Gate |
|-------|-------|----------|-----------|
| **0** | Validation — narrowest possible agent, one pipeline, 5 real users | ~90 days | ≥3/5 design partners reach for a credit card |
| **1** | MVP hardening + first paying design partners | ~Months 4–7 | ≥3 paying partners, self-heal rate target met |
| **2** | Expand to 2–3 pipelines + reproducibility/provenance + team plans | ~Months 7–12 | Multi-pipeline retention + team-plan revenue |
| **3** | Platform, scale, data flywheel, enterprise/biotech | ~Months 12+ | Repeatable enterprise motion + improving accuracy from data |

---

## Phase 0 — Validation (90 Days)

**Objective:** Prove that real bioinformaticians will pay for an agent that runs ONE pipeline end-to-end and self-heals the common failures — on their own data.

**Decision philosophy:** This phase is an experiment, not a product launch. Optimize for *learning whether to continue*, not for code quality or coverage.

### Pipeline choice (Week 1, locked)
Choose **ONE** of:
- **RNA-seq differential expression** (high-volume, extremely well-documented, painful at the stats/QC stages), or
- **Germline variant calling** (high-volume, GATK best-practices well-defined, painful in reference/format wrangling).

Recommendation: **RNA-seq differential expression** unless early discovery (Week 1–2) skews toward variant calling. RNA-seq DE has the largest population of non-programmer wet-lab users — the exact ICP where "can't code" pain is highest [nature.com/articles/s41598-025-25919-z].

### Milestones

| Week | Milestone | Deliverable | Success Signal |
|------|-----------|-------------|----------------|
| 1 | Lock pipeline + define the "happy path" | Written spec: inputs (e.g. FASTQ + sample sheet + reference), steps, expected outputs | Spec reviewed by ≥1 practicing bioinformatician |
| 1–2 | Identify top-5 failure modes | Failure catalog (e.g. malformed sample sheet, reference/genome mismatch, OOM/resource limits, missing index, version/dependency conflict) | 5 named, reproducible failure modes with triggers |
| 2–4 | Build narrowest end-to-end agent | Agent ingests real input → runs pipeline on real compute → returns result | One full clean run on a public dataset (e.g. a known GEO/SRA RNA-seq set) |
| 4–6 | Self-heal the top-5 failures | Detection + recovery for each cataloged failure | Agent recovers from ≥4/5 injected failures without human help |
| 5–6 | Verification + reproducibility layer (minimal) | Output verification checks + a reproducible run manifest (versions, params, container/env hash, command log) | A second run reproduces the first bit-for-bit (or within documented tolerance) |
| 6–7 | Recruit 5 design partners | 5 confirmed real bioinformaticians scheduled | 5 booked sessions (see GTM playbook) |
| 7–10 | Watch them use it on THEIR data | Recorded/observed sessions, notes per user | Each completes (or fails informatively) a real analysis |
| 9–10 | **The money question** | WTP script run with all 5 | Credit card OR a clear, reasoned "no" from each |
| 10 | **DECISION GATE** | Go/no-go memo | See gate below |

### Phase 0 Success Metrics
- **Self-heal rate:** ≥4/5 of the cataloged failure modes recovered autonomously.
- **End-to-end completion:** ≥4/5 design partners get a usable result on their own data (with or without minor intervention).
- **Reproducibility:** 100% of completed runs produce a manifest that reproduces the result.
- **The only metric that decides the company:** WTP responses.

### 🚦 Phase 0 → Phase 1 Gate
- **PROCEED** if **≥3/5 design partners reach for a credit card** (give a card, sign a paid pilot, or give an unambiguous "yes, I/my lab would pay $X from [named budget]").
- **PIVOT** if fewer than 3. Re-examine: wrong pipeline? wrong ICP? value not in verify/reproduce? willingness exists but budget owner is elsewhere? Use discovery notes to choose the next experiment — do **not** add features and hope.

---

## Phase 1 — MVP Hardening + First Paying Partners

**Objective:** Turn the validation prototype into something the first paying design partners run on their real workflows repeatedly, without it embarrassing us.

**Scope discipline:** Still ONE pipeline. We are deepening, not widening.

### Goals
- Convert ≥3 Phase-0 yeses into paying design partners under a simple paid-pilot agreement.
- Make the agent reliable enough to use unattended on real, messy data.
- Expand the failure-mode coverage well beyond the original top-5 as real-world breakage surfaces.

### Key Deliverables

| Area | Deliverable |
|------|-------------|
| Reliability | Failure-mode catalog expanded to top ~15–20; self-heal coverage for each |
| Compute | Clean integration with the partners' actual compute (local workstation, SLURM/HPC, and/or one cloud target) |
| Verification | Hardened output verification (sanity checks, QC thresholds, biological plausibility checks appropriate to the pipeline) |
| Reproducibility | Run manifest + one-click re-run; exportable methods summary suitable for a paper's Methods section |
| Onboarding | A non-programmer wet-lab scientist can go from raw data → result with no CLI use |
| Billing | Minimal paid mechanism (Stripe, usage- or seat-based — see GTM) |
| Observability | Internal telemetry on runs, interventions, failures (to measure the metrics below) |

### Success Metrics
- **Runs completed without human intervention:** ≥70% of real runs.
- **Paying design partners:** ≥3 actively paying.
- **Time-to-first-result** for a new user: under one working day.
- **Retention:** partners run ≥2 analyses/month.
- **Methods-export usage:** partners actually use the reproducibility artifact (proxy for the verify/reproduce moat being valued).

### 🚦 Phase 1 → Phase 2 Gate
- ≥3 paying partners retained for ≥2 months, **and**
- ≥70% unattended completion on the core pipeline, **and**
- ≥2 partners explicitly request a second pipeline (demand-pull, not our guess).

---

## Phase 2 — Expand Pipelines + Reproducibility/Provenance + Team Plans

**Objective:** Prove the Layer-2 engine generalizes beyond one pipeline, and that the reproducibility/provenance layer is a paid differentiator — not a nicety.

### Goals
- Add **2–3 more pipelines**, chosen by partner demand-pull from Phase 1 (likely candidates: the *other* of RNA-seq DE / variant calling, plus single-cell RNA-seq or 16S/metagenomics).
- Turn reproducibility into first-class **provenance**: full lineage, audit trail, signed/immutable run records.
- Introduce **team plans** (shared workspaces, shared pipeline configs, role-based access).

### Key Deliverables

| Area | Deliverable |
|------|-------------|
| Pipelines | 2–3 additional pipelines on the same run/debug/self-heal/verify engine |
| Generalization | A pipeline-onboarding framework so adding a pipeline is weeks, not a rewrite (ideally building on nf-core where it fits) |
| Provenance | End-to-end lineage: inputs → tools → versions → params → outputs, queryable and exportable |
| Audit/compliance | Immutable run logs; export formats acceptable for publication and audit |
| Team plans | Shared workspaces, seat management, shared/locked pipeline templates |
| Self-serve | Smoother self-serve signup + onboarding for the bottoms-up motion |

### Success Metrics
- **Multi-pipeline adoption:** ≥40% of active accounts use ≥2 pipelines.
- **Unattended completion** holds ≥75% across all supported pipelines.
- **Team-plan revenue:** first team-plan accounts converted; expansion revenue measurable.
- **Net revenue retention** > 100% on early cohorts.
- **Provenance pull:** accounts citing reproducibility/provenance as a top-3 reason to stay (from check-ins/NPS).

### 🚦 Phase 2 → Phase 3 Gate
- Multi-pipeline retention proven (NRR > 100% on a cohort), **and**
- At least one **core facility or biotech** converts to a team/org plan (validates the move up-market), **and**
- Pipeline-onboarding framework demonstrably reduces time-to-add a pipeline.

---

## Phase 3 — Platform, Scale, Data Flywheel, Enterprise/Biotech

**Objective:** Become the default Layer-2 execution/verification platform; compound a data advantage; land enterprise/biotech.

### Goals
- **Data flywheel:** every run (failures, fixes, verifications) — with consent and privacy controls — improves self-heal and verification. This is where our BixBench-style accuracy advantage compounds: our edge is *learned from real failures*, not from a static model [arxiv.org/abs/2503.00096].
- **Enterprise/biotech motion:** SSO, on-prem/VPC deployment, compliance (audit, data residency), SLAs.
- **Platform:** stable interfaces for partners/core facilities to register their own pipelines and validation rules.

### Key Deliverables

| Area | Deliverable |
|------|-------------|
| Flywheel | Consented failure/fix corpus; measurable improvement in self-heal & verification accuracy over time |
| Enterprise | SSO, VPC/on-prem deploy, audit logs, data-residency controls, SLAs |
| Platform | Self-registration of pipelines + custom verification rules; partner ecosystem |
| Scale | Multi-tenant infra, cost controls, large-cohort throughput |
| Trust | Independent benchmark results (our accuracy vs. BixBench-style baselines) published as proof |

### Success Metrics
- **Self-heal/verification accuracy** improving quarter-over-quarter from the flywheel (tracked against a held-out internal benchmark).
- **Enterprise/biotech logos** with repeatable sales motion (≥3 closed, cycle time trending down).
- **Gross margin** healthy despite running on customer compute (our cost is orchestration, not raw compute).
- **Published benchmark** showing materially better-than-baseline accuracy on real analytical tasks.

---

## Risks & Assumptions Register

| # | Risk / Assumption | Tied to | Likelihood | Impact | Mitigation / Test |
|---|-------------------|---------|-----------|--------|-------------------|
| R1 | **WTP doesn't exist** — people want it free, won't pay or it's no one's budget | Phase 0 gate | Med | Fatal | The whole Phase 0 WTP script; pivot rule baked into the gate |
| R2 | **Wrong pipeline chosen** — low pain or low volume | Wk1 pipeline lock | Med | High | Validate pipeline choice with ≥1 practitioner Wk1; pick highest non-programmer pain (RNA-seq DE) |
| R3 | **Self-heal is harder than the top-5** — real data breaks in long-tail ways | Wk4–6; Phase 1 | High | High | Catalog failures empirically from real runs; expand catalog continuously; measure unattended-completion rate |
| R4 | **Verification gives false confidence** — agent says "verified" but result is wrong | Phase 0 verify layer onward | Med | Fatal (trust) | Conservative checks; surface uncertainty; never claim verified beyond what checks cover; expert spot-checks in Phase 0/1 |
| R5 | **Reproducibility not valued enough to pay for** | Phase 1/2 | Med | High | Measure methods-export & provenance usage; if unused, re-test value prop before investing further |
| R6 | **Can't recruit 5 real bioinformaticians** | Wk6–7 | Med | High | Start outreach Wk1 in parallel; multiple channels (Biostars, r/bioinformatics, X bio, nf-core Slack, core facilities) |
| R7 | **Engine doesn't generalize** — each pipeline is a rewrite | Phase 2 gate | Med | High | Build pipeline-onboarding framework; lean on nf-core; gate Phase 2 on demonstrated reuse |
| R8 | **Running on customer compute is too brittle/varied** (HPC vs cloud vs laptop) | Phase 1 compute | High | Med | Start with ONE compute target per partner; expand deliberately; abstract late |
| R9 | **Layer 1 vendors move into Layer 2** | All phases | Med | High | Move fast on the verify/reproduce moat + data flywheel; community trust as a defensive moat |
| R10 | **Founder lacks wet-lab/clinical credentials** — trust gap, esp. clinical | GTM + Phase 3 | Med | Med | Avoid clinical/diagnostic claims early; recruit advisory bioinformaticians; let verified runs + community reputation speak |
| R11 | **Data governance blocks biotech** | Phase 3 enterprise | Med | High | "Runs on your compute / your data never leaves" as core architecture from day 1; VPC/on-prem in Phase 3 |
| R12 | **Flywheel needs consent that customers won't give** | Phase 3 | Med | Med | Opt-in, privacy-preserving (share failure patterns/metadata, not raw data); make value of contributing obvious |

---

## One-line phase mantra
**Phase 0:** earn one credit card. **Phase 1:** keep three. **Phase 2:** prove it generalizes. **Phase 3:** make every run make the next one smarter.
