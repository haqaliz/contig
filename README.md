# Contig

**An agentic bioinformatics analyst.**

Contig ingests a researcher's raw sequencing data, selects and runs the right pipeline on their compute, debugs and self-heals failures, and returns a verified, reproducible result.

---

## What is Contig

A "contig" in genomics is one contiguous sequence reconstructed by assembling many overlapping fragments - scattered reads stitched into a coherent whole. Contig the product does the same thing for an analysis: it assembles messy data, scattered tools, and broken steps into one verified working result.

Contig is not a chatbot that writes you a script. It is an agent that takes the analysis all the way to a trustworthy answer - running the workflow on real data and real compute, fixing what breaks, and proving the result is correct and reproducible.

---

## The problem

Bioinformatics has a structural skills gap. Producing an end-to-end analysis from raw sequencing data requires a rare combination of domain biology *and* software/computational engineering - a pairing few individuals hold.

- Roughly **74% of wet-lab scientists have no programming experience** ([arxiv.org/html/2507.20122v1](https://arxiv.org/html/2507.20122v1)).
- Domain scientists without programming face steep learning curves, and building end-to-end pipelines needs the scarce dual genomics+computation skill set ([arxiv.org/html/2507.20122v1](https://arxiv.org/html/2507.20122v1); [nature.com/articles/s41598-025-25919-z](https://www.nature.com/articles/s41598-025-25919-z)).
- In practice, researchers scavenge Biostars Q&A threads and paper methods sections to piece pipelines together by hand ([arxiv.org/html/2507.20122v1](https://arxiv.org/html/2507.20122v1)).

The result is slow science, brittle analyses, and results that are hard to reproduce.

---

## The solution - and the wedge

There are two layers to "AI for bioinformatics," and they are not the same business.

### Layer 1 - Translate English into a script/workflow
Turning a natural-language request into a Galaxy/Nextflow workflow or a script. This layer is **crowded and commoditizing**: Galaxy, KNIME, BioMaster, BioWorkflow, and general-purpose LLMs all do it, and frontier models do it increasingly well. **Contig does not compete here.**

### Layer 2 - Actually run it, debug it, self-heal, verify, and guarantee reproducibility
End-to-end, on the user's own data and compute. Run the pipeline. When a step fails - wrong reference, version mismatch, malformed input, out-of-memory - diagnose it and recover. Then verify the output is correct and produce a reproducible artifact. This layer is **essentially unsolved and barely contested. This is the company.**

The evidence that Layer 2 is the real moat:

- LLMs (GPT-4o, Gemini 2.5 Flash, DeepSeek-V3) already generate technically accurate Galaxy/Nextflow workflows from natural language; small models + RAG over docs reach expert level on the *conceptual* layer - no massive compute or special credentials required. The conceptual layer is solved-enough.
- But current systems match experts only on **easy** tasks and **fail on medium/complex** workflows. On BixBench - a benchmark of real bioinformatics analysis - frontier models reach only **~17% accuracy** ([arxiv.org/abs/2503.00096](https://arxiv.org/abs/2503.00096)). The hard execution-and-verification layer is where everyone falls down, which is exactly why it is the moat.

**Key risk we design around:** foundation models will keep improving and may close part of the Layer-2 gap. So Contig's defensibility is built from **execution / verification / reproducibility infrastructure** plus **accumulated workflow-evaluation data** - not from prompting. We are building the part of the system that gets *better* as models improve, not the part they make obsolete.

---

## Who it's for

- The lone **computational biologist** drowning in pipeline plumbing instead of doing science.
- The **wet-lab scientist who can't code** but has data and questions.
- **Core facilities** that run analyses as a service for many labs.
- **Biotech** R&D teams that need reproducible, auditable results.

---

## Current status

**MVP engine built; validating.** The Layer-2 core - run → capture → **self-heal** → verify → reproduce - works end-to-end as a CLI on one pipeline (`nf-core/rnaseq`), built test-first (see [Getting started](#getting-started)). The problem and strategic wedge were adversarially fact-checked through deep research ([docs/RESEARCH_FINDINGS.md](docs/RESEARCH_FINDINGS.md)). Next: willingness-to-pay validation with design partners, and breadth - see [docs/ROADMAP.md](docs/ROADMAP.md).

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

To run a real pipeline you also need **Nextflow** (`brew install nextflow`), a
**Java runtime** (`JAVA_HOME` set to a JDK, e.g. Homebrew's `openjdk`), and a
running **Docker** daemon. The commands and the test suite work without them.

### Commands

| Command | What it does |
|---|---|
| `contig plan --goal "…" --input <sheet>` | Propose a pipeline + params from your goal and data, to approve |
| `contig run --run-id <id>` | Run a pipeline, self-heal failures, verify, report the verdict |
| `contig show <id>` | The verdict + provenance + repair chain of a past run |
| `contig list` | All bundled runs |
| `contig version` | Installed version |

### Try it in 30 seconds (no real data)

```bash
uv run contig run --run-id smoke      # runs nf-core/rnaseq's bundled test profile
uv run contig show smoke              # see the verdict + repair chain
```

### Run on your own data

**1. Write a sample sheet** (`samplesheet.csv`, nf-core/rnaseq format). Paths may
be relative to the sheet:

```csv
sample,fastq_1,fastq_2,strandedness
CTRL_REP1,reads/ctrl1_R1.fastq.gz,reads/ctrl1_R2.fastq.gz,auto
TREAT_REP1,reads/treat1_R1.fastq.gz,reads/treat1_R2.fastq.gz,auto
```

**2. (Optional) Plan first.** Describe your goal in plain language and let Contig
propose a pipeline + params to approve - it flags problems (no replicates,
single-end, missing reference) *before* you run, and declines goals it has no
curated pipeline for rather than inventing a workflow:

```bash
uv run contig plan --goal "find differentially expressed genes" \
  --input samplesheet.csv --genome GRCh38
# → Plan: nf-core/rnaseq @ 3.26.0  (assay: rnaseq) … + any warnings
```

The goal→pipeline matching is deterministic and **replaceable** - a better model
can be swapped in behind it. Contig's value is the curated registry and the
run/verify/reproduce engine, not generating workflows from English (that's a
commodity it consumes - see [VISION.md](VISION.md)).

**3. Run it**, pointing at a reference - an iGenomes key **or** your own FASTA+GTF:

```bash
uv run contig run --run-id my-analysis \
  --input samplesheet.csv \
  --genome GRCh38                       # or: --fasta ref.fa --gtf genes.gtf
```

Contig first **validates the sample sheet** (missing files, duplicate samples,
bad columns) and refuses to launch if it's broken - catching the error before it
costs you a multi-hour run. Then it runs the pipeline, **self-heals** recoverable
failures, **verifies** the output, and writes a reproducible bundle. Your reads
never leave your machine - only file hashes are recorded.

### Reading the result

Every run ends in an honest verdict:

| Verdict | Meaning |
|---|---|
| `PASS` | Ran to completion and every QC check passed |
| `WARN` | Completed, but a QC check is borderline - look before you trust it |
| `FAIL` | A task failed, or a QC check failed - do not trust the output |
| `UNVERIFIED` | Completed but nothing checked it - we won't claim it's correct |

If a step broke and Contig recovered, the report shows the **repair chain**
(e.g. `attempt 1: oom → resource patch → patched_and_retried`).

### Reproduce / share

Each run writes `runs/<id>/run_record.json` - a portable record pinning inputs
(checksums), pipeline + revision, parameters, container/tool versions, every QC
result, and the full repair chain. `contig show <id>` re-reads it; hand the
bundle to a colleague (or a reviewer) to reproduce the result.

### Where it runs (compute backends)

The same run lands unchanged on your laptop or your cloud - Contig maps the
target to a generated `nextflow.config` and lets Nextflow's native executors do
the submission. Pick the backend with `--backend`:

```bash
# Local (default) - Docker on your machine
uv run contig run --run-id local-run --input samplesheet.csv --genome GRCh38

# AWS Batch - runs in your account; reads stay in your S3, not ours
uv run contig run --run-id cloud-run \
  --input samplesheet.csv --genome GRCh38 \
  --backend aws_batch \
  --work-dir s3://your-bucket/contig-work \
  --queue your-batch-queue --region eu-west-1
```

Contig validates the backend up front - e.g. an `aws_batch` run with no `--queue`
fails immediately with a clear message, not a half-hour in. AWS credentials are
read from your environment by Nextflow; Contig never holds them. The generated
config is written to `runs/<id>/nextflow.config` for inspection. (`local` and
`aws_batch` are wired today; `slurm`/`gcp_batch`/`k8s` map through the same layer
as they're validated.)

### Supported analyses

| Goal | Pipeline | QC |
|---|---|---|
| RNA-seq differential expression | `nf-core/rnaseq` | alignment/assignment rate, library-size skew, replicate checks |
| Germline variant calling (research) | `nf-core/sarek` | Ti/Tv & het/hom ratios, coverage |

`contig plan --goal "…"` routes to the right one (and declines goals it has no
curated pipeline for). The same run → self-heal → verify → reproduce engine
serves both.

### What's not built yet

A web UI, an LLM-backed planner (the goal→pipeline matcher is deterministic and
replaceable today), more assays, and live-tested `slurm`/`gcp_batch`/`k8s`
backends (the mapping layer is in place; `local` and `aws_batch` are wired). See
[docs/ROADMAP.md](docs/ROADMAP.md).

New here? Read [VISION.md](VISION.md) and [docs/RESEARCH_FINDINGS.md](docs/RESEARCH_FINDINGS.md)
for the bet, then [docs/technical/ARCHITECTURE.md](docs/technical/ARCHITECTURE.md)
for the system design.
