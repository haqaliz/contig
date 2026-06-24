# Contig: Use-Case Universe (what we can run and verify)

This document maps the broad space of bioinformatics analyses Contig can serve,
and draws the bright line we will not cross. It answers the recurring question
"can Contig detect disease, analyze sequences, do more?" honestly.

Read this together with the [`CAPABILITY_ROADMAP.md`](CAPABILITY_ROADMAP.md)
(the next six months of engine work) and the strategic guardrails in `CLAUDE.md`,
`VISION.md`, and `FEATURES.md`.

---

## The one principle that decides everything

**Contig is an assay-agnostic Layer-2 harness.** It runs a bioinformatics
pipeline on the user's data and compute, self-heals failures, verifies the output
is correct and reproducible, and records provenance. It is *not* the source of the
biological or clinical interpretation.

So "broader use cases" means **more analysis types we can run and verify**, not
**new claims we make about a person's health.** Every expansion below is an assay:
a pipeline we consume (almost always from nf-core or an established tool), plus the
verification logic that proves it ran correctly. The interpretation layer
(is this variant pathogenic, does this patient have this disease) stays with the
researcher, the annotation databases, and the regulated clinical lab.

This is not a limitation we regret. It is the moat. Anyone can run an annotation
pipeline; we win by proving the run was correct and reproducible, across more and
more analysis types.

---

## The bright line: research-use verification, not clinical diagnosis

| We DO (Layer-2, inside the founder's edge) | We DO NOT (rejected by the thesis) |
|---|---|
| Run and verify a variant-calling-and-annotation pipeline | Issue a clinical diagnosis or a "you have disease X" verdict |
| Prove the pipeline executed correctly and reproducibly | Act as an FDA/IVD device or a CLIA/CAP clinical test |
| Surface what the annotation tools reported (research use) | Interpret clinical significance as our own judgement |
| Capture provenance for a researcher's Methods section | Generate a clinical report a physician acts on |
| Support infectious-disease and oncology *research* pipelines | Make screening, prognosis, or treatment claims |

**Why the line is where it is.** Diagnosis requires wet-lab/clinical credentials,
regulatory validation, and accepts clinical liability. CLAUDE.md constraint #4 and
the FEATURES.md guardrails put all three outside the founder's edge on purpose.
Crossing the line does not just add risk; it changes the company into one the
founder is not positioned to run. So Contig stays the engine underneath the
researcher, never the diagnostician.

**How we say it in product.** Verification claims are scoped per assay and never
over-claimed (the standing "no correctness over-claiming" rule). A verdict means
"this analysis ran correctly and reproducibly," never "this result is clinically
true." Annotation output is shown as "what tool X reported," attributed to the
tool and its database version, not asserted by Contig.

---

## The assay menu (what "do more" actually looks like)

Each row is a candidate assay for the same run, self-heal, verify, reproduce
engine. Status reflects what is already on the engine. Pipelines named are the
ones we would consume, not build. Verification notes are what makes each one a
real Layer-2 win rather than a passthrough.

### Already on the engine
- **Bulk RNA-seq** (nf-core/rnaseq): expression quantification and QC.
- **Single-cell RNA-seq** (nf-core/scrnaseq): per-cell quantification.
- **Germline variant calling** (GATK best-practices via nf-core/sarek): SNV/indel
  calls with QC.

### Variant analysis (the family closest to "disease research")
- **Somatic / tumor-normal variant calling** (nf-core/sarek somatic): cancer
  research. Verify: VAF distribution sanity, panel-of-normals filtering present,
  concordance with a second somatic caller. (This is C4 in the capability roadmap.)
- **Variant annotation and prioritization** (VEP / SnpEff against ClinVar, gnomAD):
  attach functional and population context to calls. We run and verify the
  annotation step and show what the databases reported, with their versions, as
  research output. We do not adjudicate pathogenicity ourselves.
- **Structural variants and copy-number** (Manta, GRIDSS, CNVkit): larger events
  germline or somatic. Verify: expected event-size and count bands, breakend
  sanity.
- **Pharmacogenomics research panels (PGx)**: genotype known PGx loci. Research
  use, attributed to the star-allele caller and its database; not a prescribing
  tool.
- **Trio / rare-disease research analysis**: inheritance-pattern filtering across a
  family. Research-use prioritization, not a clinical call.
- **Polygenic risk scores (PRS)** for research cohorts: compute a score from
  published weights. Verify the computation and provenance; present as a research
  metric, never a clinical risk statement.

### Microbial, metagenomic, and infectious-disease research
- **Taxonomic profiling / 16S amplicon** (nf-core/ampliseq, Kraken2): who is in the
  sample. Verify: classified-fraction sanity, expected diversity ranges.
- **Metagenomic shotgun and pathogen identification** (research/surveillance, for
  example nf-core/mag, nf-core/taxprofiler): detect and quantify organisms.
  Research and surveillance framing, not clinical infectious-disease diagnosis.
- **Antimicrobial-resistance (AMR) gene detection** (nf-core/funcscan): resistance
  determinants in isolates or metagenomes, for research and surveillance.

### Epigenomics and chromatin
- **ATAC-seq** (nf-core/atacseq): open-chromatin. Verify: TSS enrichment, FRiP,
  fragment-size periodicity.
- **ChIP-seq / CUT&RUN** (nf-core/chipseq, nf-core/cutandrun): protein-DNA binding.
  Verify: peak-count and FRiP sanity, input-control presence.
- **Bisulfite / methylation (WGBS, EM-seq)** (nf-core/methylseq): methylation
  levels. Verify: conversion-rate sanity, coverage uniformity.

### Long-read, assembly, and structure
- **Long-read (ONT/PacBio) variant calling and phasing**: a different error model
  and tool set; high failure-mode richness, strong self-heal and verify value.
- **De novo and reference-guided assembly** (nf-core/genomeassembly): build a
  genome. Verify: contiguity (N50), completeness (BUSCO), expected genome-size
  band.

### Higher-dimensional and emerging
- **Spatial transcriptomics**, **multi-omic integration**, **proteomics/mass-spec**
  (nf-core/proteomics): further out, same harness principle. Add only by demand-pull
  and only when we can verify them.

---

## How we choose what to add (the discipline)

The menu is large on purpose, but breadth is a trap if taken greedily. The rules:

1. **Demand-pull, not our guess.** Add an assay when a design partner asks for it
   (ROADMAP Phase 1 to 2 gate), not because it is on this list.
2. **Depth-first.** One assay run flawlessly and self-healing beats five that
   mostly work. Each addition is end to end via the
   [`ADD_AN_ASSAY.md`](ADD_AN_ASSAY.md) path: registry, planner match, QC,
   structural manifest, biological-plausibility checks, concordance hook, and seed
   corpus cases.
3. **Only what we can verify.** If we cannot define an honest verification for an
   assay, we do not add it; a passthrough that issues no verdict is not a Contig
   assay.
4. **It must compound the corpus.** Each assay should bring new failure modes and
   verification signals that feed moat #2.

---

## Where this connects

- The next-six-months engine work that makes these assays *verifiable* (concordance,
  biological plausibility, reference integrity) is the
  [`CAPABILITY_ROADMAP.md`](CAPABILITY_ROADMAP.md). Somatic variant calling is
  already C4 there; the rest of this menu is the longer-horizon assay backlog the
  capability work unlocks.
- The phased business plan and gates are in [`../ROADMAP.md`](../ROADMAP.md).
- The dashboard surface for all of it is [`../../FEATURES.md`](../../FEATURES.md).

---

## Guardrails (restated, because this is the doc most likely to tempt drift)

- **No clinical diagnosis, screening, prognosis, or treatment claims.** Research-use
  verification only. The clinical verdict is never ours.
- **No Layer-1 workflow authoring as a product.** We consume pipelines; we do not
  generate them from English.
- **No raw-read egress.** Every assay runs on the user's compute; only hashes and
  metadata leave the machine.
- **Nothing requiring wet-lab or clinical credentials, proprietary datasets, or
  EHR/regulatory integration** as a precondition.
- **No correctness over-claiming.** A verdict is "ran correctly and reproducibly,"
  scoped per assay, never "clinically true."
