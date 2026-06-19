# Contig

**An agentic bioinformatics analyst.**

Contig ingests a researcher's raw sequencing data, selects and runs the right pipeline on their compute, debugs and self-heals failures, and returns a verified, reproducible result.

---

## What is Contig

A "contig" in genomics is one contiguous sequence reconstructed by assembling many overlapping fragments — scattered reads stitched into a coherent whole. Contig the product does the same thing for an analysis: it assembles messy data, scattered tools, and broken steps into one verified working result.

Contig is not a chatbot that writes you a script. It is an agent that takes the analysis all the way to a trustworthy answer — running the workflow on real data and real compute, fixing what breaks, and proving the result is correct and reproducible.

---

## The problem

Bioinformatics has a structural skills gap. Producing an end-to-end analysis from raw sequencing data requires a rare combination of domain biology *and* software/computational engineering — a pairing few individuals hold.

- Roughly **74% of wet-lab scientists have no programming experience** ([arxiv.org/html/2507.20122v1](https://arxiv.org/html/2507.20122v1)).
- Domain scientists without programming face steep learning curves, and building end-to-end pipelines needs the scarce dual genomics+computation skill set ([arxiv.org/html/2507.20122v1](https://arxiv.org/html/2507.20122v1); [nature.com/articles/s41598-025-25919-z](https://www.nature.com/articles/s41598-025-25919-z)).
- In practice, researchers scavenge Biostars Q&A threads and paper methods sections to piece pipelines together by hand ([arxiv.org/html/2507.20122v1](https://arxiv.org/html/2507.20122v1)).

The result is slow science, brittle analyses, and results that are hard to reproduce.

---

## The solution — and the wedge

There are two layers to "AI for bioinformatics," and they are not the same business.

### Layer 1 — Translate English into a script/workflow
Turning a natural-language request into a Galaxy/Nextflow workflow or a script. This layer is **crowded and commoditizing**: Galaxy, KNIME, BioMaster, BioWorkflow, and general-purpose LLMs all do it, and frontier models do it increasingly well. **Contig does not compete here.**

### Layer 2 — Actually run it, debug it, self-heal, verify, and guarantee reproducibility
End-to-end, on the user's own data and compute. Run the pipeline. When a step fails — wrong reference, version mismatch, malformed input, out-of-memory — diagnose it and recover. Then verify the output is correct and produce a reproducible artifact. This layer is **essentially unsolved and barely contested. This is the company.**

The evidence that Layer 2 is the real moat:

- LLMs (GPT-4o, Gemini 2.5 Flash, DeepSeek-V3) already generate technically accurate Galaxy/Nextflow workflows from natural language; small models + RAG over docs reach expert level on the *conceptual* layer — no massive compute or special credentials required. The conceptual layer is solved-enough.
- But current systems match experts only on **easy** tasks and **fail on medium/complex** workflows. On BixBench — a benchmark of real bioinformatics analysis — frontier models reach only **~17% accuracy** ([arxiv.org/abs/2503.00096](https://arxiv.org/abs/2503.00096)). The hard execution-and-verification layer is where everyone falls down, which is exactly why it is the moat.

**Key risk we design around:** foundation models will keep improving and may close part of the Layer-2 gap. So Contig's defensibility is built from **execution / verification / reproducibility infrastructure** plus **accumulated workflow-evaluation data** — not from prompting. We are building the part of the system that gets *better* as models improve, not the part they make obsolete.

---

## Who it's for

- The lone **computational biologist** drowning in pipeline plumbing instead of doing science.
- The **wet-lab scientist who can't code** but has data and questions.
- **Core facilities** that run analyses as a service for many labs.
- **Biotech** R&D teams that need reproducible, auditable results.

---

## Current status

**MVP engine built; validating.** The Layer-2 core — run → capture → **self-heal** → verify → reproduce — works end-to-end as a CLI on one pipeline (`nf-core/rnaseq`), built test-first (see [Getting started](#getting-started)). The problem and strategic wedge were adversarially fact-checked through deep research ([docs/RESEARCH_FINDINGS.md](docs/RESEARCH_FINDINGS.md)). Next: willingness-to-pay validation with design partners, and breadth — see [docs/ROADMAP.md](docs/ROADMAP.md).

---

## Documentation map

| Document | What's in it |
|---|---|
| [VISION.md](VISION.md) | The narrative thesis, the moat, why now, non-goals |
| [docs/RESEARCH_FINDINGS.md](docs/RESEARCH_FINDINGS.md) | The validated evidence base behind the bet |
| [docs/ROADMAP.md](docs/ROADMAP.md) | Phased plan from validation to MVP and beyond |
| [docs/product/PRODUCT_SPEC.md](docs/product/PRODUCT_SPEC.md) | Product surface, flows, and behavior |
| [docs/technical/ARCHITECTURE.md](docs/technical/ARCHITECTURE.md) | The agentic execution/verification system design |
| [docs/business/MARKET_ANALYSIS.md](docs/business/MARKET_ANALYSIS.md) | Market, competitors, and positioning |
| [docs/business/BUSINESS_MODEL.md](docs/business/BUSINESS_MODEL.md) | Revenue, pricing, ICP |
| [docs/business/GTM.md](docs/business/GTM.md) | Go-to-market plan |

> Note: some of these documents are placeholders to be filled in during the validation phase.

---

## Getting started

Contig is a Python 3.12 package managed with [`uv`](https://github.com/astral-sh/uv).

```bash
uv sync                 # create the venv and install deps
uv run pytest           # run the full test suite
```

### The CLI

```bash
uv run contig --help                     # version | plan | run | show | list
uv run contig run --run-id my-run        # run nf-core/rnaseq, self-heal, verify, report
uv run contig show my-run                # the verdict + provenance + repair chain of a past run
uv run contig list                       # all bundled runs
```

A real `contig run` executes `nf-core/rnaseq` via Nextflow on Docker, so it needs
**Nextflow** (`brew install nextflow`), a **Java runtime**, and a running
**Docker** daemon. Set `JAVA_HOME` to a JDK (e.g. Homebrew's `openjdk`).

### What works today (MVP)

The end-to-end **run → capture → self-heal → verify → reproduce** loop:

- runs a real pipeline on your compute and captures every task;
- on a recoverable failure (OOM, time limit, transient container error) it
  **diagnoses, applies a safe fix, and re-runs** — bounded and fully logged;
- **verifies** the result with layered QC (structural, per-sample rule pack,
  cross-sample) and emits an **honest verdict** (`pass`/`warn`/`fail`/`unverified`);
- writes a **reproducible bundle** (`run_record.json`) pinning inputs, versions,
  parameters, QC, and the full repair chain.

Not yet built: the natural-language planning layer (you specify the pipeline),
a web UI, and breadth beyond RNA-seq. See [docs/ROADMAP.md](docs/ROADMAP.md).

New here? Read [VISION.md](VISION.md) and [docs/RESEARCH_FINDINGS.md](docs/RESEARCH_FINDINGS.md)
for the bet, then [docs/technical/ARCHITECTURE.md](docs/technical/ARCHITECTURE.md)
for the system design.
