# Contig - Vision

> Every scientist should have a reliable computational analyst. Today, almost none of them do.

---

## The bet in one sentence

The valuable, defensible problem in AI-for-bioinformatics is not *writing* the workflow - it is **running it, healing it when it breaks, verifying the output, and guaranteeing reproducibility** end-to-end on the user's data and compute. Contig is the company that builds that layer.

---

## The founder's unfair advantage

Producing a working bioinformatics analysis requires a rare pairing of skills: genomics domain knowledge *and* real software/computational engineering. That scarcity is the entire problem (building end-to-end pipelines needs this dual expertise - [arxiv.org/html/2507.20122v1](https://arxiv.org/html/2507.20122v1); [nature.com/articles/s41598-025-25919-z](https://www.nature.com/articles/s41598-025-25919-z)).

Contig's founder sits at an unusual intersection:

- **Full-stack developer** - can build the real product, not just a prototype.
- **ML engineer** - can build the agentic system and the evaluation/verification machinery.
- **Genetics passion** - understands the domain and the workflows deeply enough to know what "verified" actually means.

The crucial point: **the moat is engineering, and engineering is the founder's edge.** Contig deliberately does *not* depend on assets the founder lacks - there are no wet-lab or clinical credentials, no proprietary biological dataset, no regulatory standing required to win the Layer-2 execution problem. The hard part is infrastructure, and that is exactly the part this founder is best positioned to build.

---

## Why now

- **The conceptual layer is feasible today.** LLMs (GPT-4o, Gemini 2.5 Flash, DeepSeek-V3) already generate technically accurate Galaxy/Nextflow workflows from natural language, and small models + RAG over docs reach expert level on the conceptual layer - no massive compute or credentials needed.
- **The hard layer is still wide open.** Current systems match experts only on easy tasks and fail on medium/complex workflows; frontier models reach only **~17% accuracy** on real bioinformatics analysis (BixBench, [arxiv.org/abs/2503.00096](https://arxiv.org/abs/2503.00096)). The execution-and-verification gap is real, measurable, and barely contested.
- **The thesis is funded.** "AI agents for science" is a hot current investment thesis, and the moat here is engineering - the founder's strength.

The window is the gap between "models can draft a workflow" and "anyone has made the full run trustworthy." That gap is open right now.

---

## The long-term vision

If Contig wins, the picture is simple: **every scientist has a reliable computational analyst on demand.**

A wet-lab biologist drops in raw sequencing data, states the question in plain English, and gets back a verified, reproducible result - without learning to code, without scavenging Biostars threads, without hiring a scarce bioinformatician for plumbing. Core facilities run an order of magnitude more analyses with the same staff. Biotech R&D trusts its pipelines because every result ships with a reproducible, auditable trail.

The bottleneck on biological discovery stops being "can someone make the pipeline run correctly," and the rare genomics+computation experts are freed to do novel science instead of debugging version mismatches.

---

## The strategic moat narrative

> Build the part that gets **better** as foundation models improve, not the part they make obsolete.

The clear risk to any AI-for-bioinformatics company is that foundation models keep improving and absorb the easy work. Prompt-wrapper companies get erased by the next model release. Contig is structured to **benefit** from that trajectory:

1. **Execution / verification / reproducibility infrastructure.** The harness that runs real pipelines on real compute, isolates and diagnoses failures, self-heals, and proves correctness. Better base models make a *better orchestrator* inside this harness - they do not replace the harness.
2. **Accumulated workflow-evaluation data.** Every run - every failure, every fix, every verified output - feeds a proprietary corpus of what works, what breaks, and how to recover. This data compounds and cannot be prompted into existence. It is the asset competitors cannot copy and that improves with scale.

The moat is **infrastructure + data**, explicitly **not prompting**.

---

## Non-goals

Contig will **not**:

- **Build Layer 1** (natural-language-to-workflow) as a product. It is crowded and commoditizing (Galaxy, KNIME, BioMaster, BioWorkflow, general LLMs). Contig consumes this capability; it does not sell it.
- **Compete as "a better LLM"** or rely on a prompting edge as its defensibility.
- **Take on wet-lab or clinical-credential-gated work.** That is outside the founder's edge and the company's wedge.
- **Pursue heavy regulatory/integration plays** as the opening move (see below).
- **Become a generic data-science notebook** or a general workflow-automation tool. The scope is end-to-end bioinformatics analysis, run and verified.

---

## Why not the alternatives

Several adjacent genomics product ideas were considered and rejected. They are useful as a map of where *not* to go:

- **DNA-to-face / phenotype prediction** - blocked by proprietary datasets. The data needed to win is locked up; the founder cannot acquire it.
- **Spatial transcriptomics tooling** - blocked by a strong free incumbent (STOmicsDB). Hard to displace "good and free."
- **CRISPR off-target prediction** - crowded, and competing against free resources like the CRISPRoffT database. No durable wedge.
- **Pharmacogenomics (PGx) EHR middleware** - likely the best *revenue* path, but carries a heavy integration and regulatory burden that does not match a solo/small-team founder without clinical credentials. Wrong first move.

Each of these fails on at least one of: *proprietary-data dependency*, *strong free incumbent*, or *regulatory/integration burden the founder can't carry.* The Layer-2 execution problem fails on none of them - which is precisely why it is the company.

---

## What success looks like for Contig itself

A sustainable software business - per-seat SaaS plus usage on managed compute - sitting on a compounding workflow-evaluation dataset and a hardened execution layer. And a clear roster of natural acquirers if that path is taken: AWS HealthOmics, Google Cloud Life Sciences, DNAnexus, Terra/Broad, Illumina, Seqera/Nextflow, Latch Bio, and pharma R&D. But the goal is to build the indispensable layer first; everything else follows from owning the part of the stack that gets stronger over time.
