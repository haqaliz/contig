# Contig — Validated Research Findings

> The adversarially fact-checked research dossier behind choosing the Contig idea over 9 alternatives. This is the evidence base future decisions rest on.

**Original question:** Compare 10 startup ideas at the intersection of full-stack dev + ML + genetics/biology to find the most attractive for a solo / small-team, software-first founder with **no wet-lab or clinical credentials**.

**Verification rigor:** 24 sources fetched · 111 claims extracted · 25 fact-checked · **23 confirmed / 2 killed**.

---

## Executive Summary

Of the ten candidate ideas, only five produced **any** surviving, independently-verified claims after adversarial review. The other five were not disqualified — they were simply **unassessed** (absence of evidence, not evidence of absence).

The decisive lens for a software-first solo founder is the **data moat**: ideas whose defensibility depends on a proprietary dataset that requires biobank recruitment, IRB approval, or scanning hardware are effectively blocked, while ideas where the moat lives in **software, integration, and workflow** are viable.

- **Idea #4 (bioinformatics NL-to-workflow copilot)** is the best founder fit: a rigorously validated problem, tech that is feasible *today* for a software founder using small models + RAG, and real defensibility headroom because reliable pipeline generation is still unsolved.
- **Idea #7 (pharmacogenomics EHR middleware)** is the best near-term revenue path: a severe, validated clinical pain point with a free, structured, standardized clinical-content base (CPIC) — moat shifts to integration and EHR-CDS workflow.
- **Idea #5 (CRISPR off-target predictive API)** is feasible but academically crowded with a strong free public database; defensibility requires a commercial wedge beyond sequence-only models.
- **Ideas #1 (DNA-to-3D face)** and **#9 (spatial transcriptomics)** are blocked by data moats a software-first founder cannot cross.

### Final Ranking

| Rank | Idea | One-line verdict |
|------|------|------------------|
| **1st** | **#4 — Bioinformatics NL-to-workflow copilot** | Best **founder fit**: validated problem, feasible today, real defensibility headroom |
| **2nd** | **#7 — Pharmacogenomics EHR middleware** | Best **near-term revenue**: severe validated problem, free standardized content, integration moat |
| **3rd** | **#5 — CRISPR off-target predictive API** | Crowded but feasible; needs a defensible commercial wedge |
| — | **#1 — DNA-to-3D facial reconstruction** | **Data-moat-blocked** for software-first founder |
| — | **#9 — Spatial transcriptomics pattern engine** | **Data-moat-blocked** by free incumbent |
| — | #2, #3, #6, #8, #10 | **Unassessed** — no surviving verified claims (not disqualified) |

**Ranking shorthand:** #4 (best founder fit) > #7 (best near-term revenue) > #5 (crowded but feasible) >> #1 / #9 (data-moat-blocked).

---

## Per-Idea Verdicts

### #4 — Bioinformatics NL-to-workflow copilot — ✅ TOP PICK (best founder fit)
A copilot that turns natural-language requests into executable bioinformatics workflows (e.g. Galaxy / Nextflow pipelines).

- **Problem:** Validated and well-known. ~74% of wet-lab scientists have no programming experience; end-to-end workflow building demands rare dual genomics+computation expertise; practitioners scavenge Q&A platforms (Biostars) and paper methods sections.
- **Feasibility:** Achievable today. LLMs (GPT-4o, Gemini 2.5 Flash, DeepSeek-V3) already generate technically accurate, executable workflows from NL. A software founder can reach expert-level on the conceptual layer with small models (Phi-3) + RAG over docs — no massive compute or credentials.
- **Defensibility:** Real headroom. Reliable working pipeline/code generation is unsolved — systems match experts only on EASY tasks and fail on medium/complex ones (BixBench: frontier models ~17% open-answer accuracy on real analysis). The solution space is populated (Galaxy, KNIME, BioMaster, BioWorkflow, AI copilots) — feasible-and-defensible, but **not uncontested**.
- **Watch-outs:** Willingness-to-pay and sales cycle are open (academic/grant-funded low-ACV vs biotech/pharma higher-ACV/longer-cycle); evidence rests on small-sample mid-2025 preprints.

### #7 — Pharmacogenomics (PGx) EHR middleware — ✅ STRONG (best near-term revenue)
Middleware that surfaces PGx guidance into EHR prescribing workflows as clinical decision support.

- **Problem:** Severe and validated. ~98% of clinicians agree genes affect drug response, but only ~10% feel adequately informed and ~75% aren't confident using PGx results in prescribing.
- **Clinical content / defensibility:** CPIC guidelines (34 genes, 164 drugs, 28 active guidelines) are the de facto global standard, freely available as a structured database with an API (Creative Commons / public domain). So content is **not** the moat — defensibility shifts to integration, normalization, and EHR-CDS workflow. Must also integrate DPWG/FDA (CPIC and FDA agreed on only 5/126 drug dosing recommendations).
- **Regulatory context:** Diagnostic-adjacent. The US LDT regime is in flux (2024 FDA LDT Final Rule vacated March 31 2025, rescinded Sept 19 2025; as of mid-2026 LDTs under enforcement discretion). Middleware positioned as **clinical decision support, not a test**, is lower-risk — but boundary management matters.
- **Watch-outs:** EHR integration barriers (Epic/Cerner App Orchard / SMART-on-FHIR certification, procurement, HIPAA/BAA) may exceed solo capacity.

### #5 — CRISPR off-target predictive API — ⚠️ FEASIBLE BUT CROWDED
An API predicting CRISPR guide-RNA off-target effects.

- **Problem:** High-stakes and well-known. Off-target effects are a critical barrier to clinical CRISPR; existing methods can't reliably predict all off-targets; >100 active genome-editing trials need off-target safety frameworks.
- **Feasibility:** Yes — transformer models work (e.g. CRISMER reports F1=0.7092, PR-AUC=0.8006).
- **Defensibility:** Weak on public data. Academically crowded (CRISPR-Net, R-CRISPR, CRISPR-M, Crispr-SGRU, BERT-based, CRISMER), with benchmark studies comparing 6–8+ methods and a FREE comprehensive public database (CRISPRoffT: 74 studies, 29 technologies, 226k pairs). Sequence-only models generalize poorly (miss chromatin/methylation).
- **Watch-outs:** Needs a defensible commercial wedge over free academic tools (enzyme/cell-type-specific, chromatin-aware, GxP/regulatory-grade reporting).

### #1 — DNA-to-3D facial reconstruction — ❌ BLOCKED (data moat)
- Below production accuracy (rank-1 ID 3.33%, verification EER 27.6% vs <1% for real biometrics).
- Binding constraint is a proprietary paired dataset (9,674 individuals with SNP + 3D facial scans, not public) requiring biobank recruitment, IRB, and scanning hardware.
- A 2026 critique notes it mostly predicts **average** sex/ancestry faces, not individuals. Effectively blocked for a software-first founder.

### #9 — Spatial transcriptomics pattern engine — ❌ BLOCKED (free incumbent)
- A strong free incumbent eliminates the data moat: **STOmicsDB** (China National GeneBank, BGI, Broad) is a free one-stop hub — 218 curated datasets, 17 species, 128 tissues, 25 spatial technologies.
- A solo founder cannot out-aggregate this on public data.

### #2, #3, #6, #8, #10 — UNASSESSED (not disqualified)
Synthetic genomic data for rare diseases (#2), microbiome-genotype cross-talk analyzer (#3), AI genomic data compression (#6), generative UI for protein design (#8), and epigenetic aging dashboard (#10) had **no surviving verified claims** after adversarial review. Their market / competition / data-moat profiles are **unknown** — this is absence of evidence, not a disqualification.

---

## Verified Findings (Full List)

Each finding records confidence, adversarial vote(s), evidence, and sources. Votes are panel tallies (confirm–dissent); some claims were voted on twice.

### Idea #4 — Bioinformatics NL-to-workflow copilot

**F1. [HIGH · vote 3-0 & 3-0] Rigorously validated problem.**
Domain scientists without programming face steep learning curves; end-to-end workflow building demands rare dual genomics+computation expertise; practitioners scavenge Q&A platforms (Biostars) and paper methods sections. Corroborated: ~74% of wet-lab scientists have no programming experience; a mature no-code ecosystem (Galaxy, KNIME) exists.
Sources: [arxiv.org/html/2507.20122v1](https://arxiv.org/html/2507.20122v1) · [nature.com/articles/s41598-025-25919-z](https://www.nature.com/articles/s41598-025-25919-z)

**F2. [MEDIUM · vote 2-1 & 2-1] Core tech is feasible today.**
LLMs (GPT-4o, Gemini 2.5 Flash, DeepSeek-V3) generate technically accurate, executable Galaxy/Nextflow workflows from NL; a software founder can reach expert-level on the conceptual layer with small models (Phi-3) + RAG over docs — no massive compute or credentials.
*Caveats:* small samples (~10 workflows, n=5 experts); prompt-dependent; hallucination requires RAG/multi-agent scaffolds; preprint / early proof-of-concept.
Sources: [arxiv.org/html/2507.20122v1](https://arxiv.org/html/2507.20122v1) · [nature.com/articles/s41598-025-25919-z](https://www.nature.com/articles/s41598-025-25919-z)

**F3. [HIGH · vote 3-0] Real defensibility headroom.**
Reliable working pipeline/code generation is unsolved — systems match experts only on EASY tasks and fail on medium/complex. Corroborated by BixBench ([arxiv 2503.00096](https://arxiv.org/abs/2503.00096)): frontier models ~17% open-answer accuracy on real bioinformatics analysis.
*Caveat:* solution space is populated (Galaxy, KNIME, BioMaster, BioWorkflow, AI copilots) — feasible-and-defensible but not uncontested.
Source: [nature.com/articles/s41598-025-25919-z](https://www.nature.com/articles/s41598-025-25919-z)

### Idea #7 — Pharmacogenomics EHR middleware

**F4. [HIGH · vote 3-0] Severe validated problem.**
~98% of clinicians agree genes affect drug response, but only ~10% feel adequately informed and ~75% aren't confident using PGx results in prescribing.
Source: [pmc.ncbi.nlm.nih.gov/articles/PMC9291515/](https://pmc.ncbi.nlm.nih.gov/articles/PMC9291515/)

**F5. [HIGH · vote 3-0 & 3-0] Limited clinical-content defensibility (moat is integration).**
CPIC guidelines (34 genes, 164 drugs, 28 active guidelines) are the de facto global standard (~85% of PGx implementation studies cite them; 128 institutions + 40 commercial labs), freely available as a structured database with an API (Creative Commons / public domain). Moat shifts to integration / normalization / EHR-CDS workflow. Must also integrate DPWG/FDA (CPIC and FDA agreed on only 5/126 drug dosing recs).
Sources: [pmc.ncbi.nlm.nih.gov/articles/PMC9291515/](https://pmc.ncbi.nlm.nih.gov/articles/PMC9291515/) · [ascpt.onlinelibrary.wiley.com/doi/10.1002/cpt.70005](https://ascpt.onlinelibrary.wiley.com/doi/10.1002/cpt.70005)

**F6. [MEDIUM · vote 3-0 & 2-1] Diagnostic-adjacent regulatory context.**
US LDT regime in flux (2024 FDA LDT Final Rule vacated March 31 2025, rescinded Sept 19 2025; as of mid-2026 LDTs under enforcement discretion). Middleware positioned as clinical decision support (not a test) is lower-risk, but boundary management matters.
Source: [pmc.ncbi.nlm.nih.gov/articles/PMC11334219/](https://pmc.ncbi.nlm.nih.gov/articles/PMC11334219/)

### Idea #5 — CRISPR off-target predictive API

**F7. [HIGH · vote 3-0 & 3-0] High-stakes, well-known problem.**
Off-target effects are a critical barrier to clinical CRISPR; existing methods can't reliably predict all off-targets; >100 active genome-editing trials need off-target safety frameworks.
Sources: [arxiv.org/pdf/2508.20130](https://arxiv.org/pdf/2508.20130) · [academic.oup.com/nar/article/53/D1/D914/7889256](https://academic.oup.com/nar/article/53/D1/D914/7889256)

**F8. [HIGH · multi-vote] Feasible but academically crowded with a free public database.**
Feasible (transformer models e.g. CRISMER report F1=0.7092, PR-AUC=0.8006) BUT crowded — many deep-learning tools (CRISPR-Net, R-CRISPR, CRISPR-M, Crispr-SGRU, BERT-based, CRISMER), benchmark studies comparing 6–8+ methods, and a FREE comprehensive public database (CRISPRoffT: 74 studies, 29 technologies, 226k pairs). Little proprietary data advantage; sequence-only models generalize poorly (miss chromatin/methylation).
Sources: [arxiv.org/pdf/2508.20130](https://arxiv.org/pdf/2508.20130) · [biorxiv.org/content/10.1101/2025.05.03.652008](https://www.biorxiv.org/content/10.1101/2025.05.03.652008) · [academic.oup.com/nar/article/53/D1/D914/7889256](https://academic.oup.com/nar/article/53/D1/D914/7889256)

### Idea #1 — DNA-to-3D facial reconstruction

**F9. [HIGH · vote 3-0 & 3-0] Effectively blocked for a software-first founder.**
Below production accuracy (rank-1 ID 3.33%, verification EER 27.6% vs <1% for real biometrics); binding constraint is a proprietary paired dataset (9,674 individuals with SNP + 3D facial scans, not public) requiring biobank recruitment, IRB, scanning hardware. A 2026 critique notes it mostly predicts average sex/ancestry faces, not individuals.
Source: [advanced.onlinelibrary.wiley.com/doi/10.1002/advs.202414507](https://advanced.onlinelibrary.wiley.com/doi/10.1002/advs.202414507)

### Idea #9 — Spatial transcriptomics pattern engine

**F10. [MEDIUM · vote 2-1 & 3-0] Strong free incumbent eliminates the data moat.**
STOmicsDB (China National GeneBank, BGI, Broad) — free one-stop hub, 218 curated datasets, 17 species, 128 tissues, 25 spatial technologies. A solo founder can't out-aggregate this on public data.
Source: [academic.oup.com/nar/article/52/D1/D1053/7416388](https://academic.oup.com/nar/article/52/D1/D1053/7416388)

### Cross-cutting (data-moat ideas)

**F11. [MEDIUM · vote 3-0 & 3-0] Public/controlled genomic data access is structural friction.**
Hurts data-moat ideas #1/#2/#3/#9: most public cancer genomic data is controlled-access; obtaining + preparing historically ~5–6 months.
*Caveat:* 2019 estimate; NIH has since streamlined dbGaP (approval now ~1–2 weeks), but download/QC time remains.
Source: [ncbi.nlm.nih.gov/pmc/articles/PMC6586850/](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC6586850/)

### Verified Findings — Quick Reference

| ID | Idea | Confidence | Vote(s) | Topic |
|----|------|-----------|---------|-------|
| F1 | #4 | HIGH | 3-0 & 3-0 | Validated problem |
| F2 | #4 | MEDIUM | 2-1 & 2-1 | Tech feasible today |
| F3 | #4 | HIGH | 3-0 | Defensibility headroom (unsolved) |
| F4 | #7 | HIGH | 3-0 | Severe validated problem |
| F5 | #7 | HIGH | 3-0 & 3-0 | Free CPIC content → integration moat |
| F6 | #7 | MEDIUM | 3-0 & 2-1 | Diagnostic-adjacent regulatory |
| F7 | #5 | HIGH | 3-0 & 3-0 | High-stakes problem |
| F8 | #5 | HIGH | multi | Feasible but crowded + free DB |
| F9 | #1 | HIGH | 3-0 & 3-0 | Blocked: proprietary dataset |
| F10 | #9 | MEDIUM | 2-1 & 3-0 | Blocked: free incumbent |
| F11 | cross | MEDIUM | 3-0 & 3-0 | Controlled-access data friction |

---

## Refuted Claims (Killed in Verification)

Recorded so they are **not reused**.

| Claim | Verdict | Vote | Source |
|-------|---------|------|--------|
| "April 2024 FDA finalized rule to phase out LDT enforcement discretion over 4–5 years" | **Refuted** — characterization wrong (rule was later vacated/rescinded) | 1-2 | [PMC11334219](https://pmc.ncbi.nlm.nih.gov/articles/PMC11334219/) |
| "Lack of standardized structured data (PDFs) is the SINGLE biggest barrier to PGx CDS adoption, making data normalization the core moat" | **Refuted** — overstated | 1-2 | [PMC9291515](https://pmc.ncbi.nlm.nih.gov/articles/PMC9291515/) |

---

## Open Questions (Carry Forward)

- **#4 willingness-to-pay & sales cycle:** academic / grant-funded (low ACV) vs biotech / pharma (higher ACV, longer cycle) — lifestyle vs venture-scale outcome?
- **#7 EHR integration barriers:** Epic/Cerner App Orchard / SMART-on-FHIR certification, procurement, HIPAA/BAA — do these exceed solo capacity?
- **#5 defensible commercial wedge:** is there one over free academic tools (enzyme/cell-type-specific, chromatin-aware, GxP/regulatory-grade reporting)?
- **#2 / #3 / #6 / #8 / #10:** unassessed — market / competition / data-moat profile unknown (absence of evidence, not disqualification).

---

## Caveats

- LLM workflow-generation capability advances monthly; cited evidence is from **mid-2025 preprints with small samples**.
- #4 and #5 (CRISMER) evidence leans on **non-peer-reviewed arXiv/bioRxiv preprints** with self-reported metrics.
- Some statistics (CPIC "global standard"; DNA-to-face accuracy) come from authors with a **vested interest**, though independently corroborated.
- The **FDA LDT landscape is volatile** — re-verify regulatory status before relying on it.

---

## Sources / Bibliography

1. [arxiv.org/html/2507.20122v1](https://arxiv.org/html/2507.20122v1) — LLM generation of bioinformatics workflows (NL → Galaxy/Nextflow).
2. [nature.com/articles/s41598-025-25919-z](https://www.nature.com/articles/s41598-025-25919-z) — Bioinformatics workflow generation / defensibility (unsolved on medium/complex).
3. [arxiv.org/abs/2503.00096](https://arxiv.org/abs/2503.00096) — BixBench: frontier models ~17% open-answer accuracy on real bioinformatics analysis.
4. [pmc.ncbi.nlm.nih.gov/articles/PMC9291515/](https://pmc.ncbi.nlm.nih.gov/articles/PMC9291515/) — PGx clinician readiness; CPIC standardization.
5. [ascpt.onlinelibrary.wiley.com/doi/10.1002/cpt.70005](https://ascpt.onlinelibrary.wiley.com/doi/10.1002/cpt.70005) — CPIC scope; CPIC vs FDA dosing-rec agreement.
6. [pmc.ncbi.nlm.nih.gov/articles/PMC11334219/](https://pmc.ncbi.nlm.nih.gov/articles/PMC11334219/) — US LDT regulatory status (Final Rule vacated/rescinded).
7. [arxiv.org/pdf/2508.20130](https://arxiv.org/pdf/2508.20130) — CRISPR off-target prediction; clinical importance.
8. [academic.oup.com/nar/article/53/D1/D914/7889256](https://academic.oup.com/nar/article/53/D1/D914/7889256) — CRISPRoffT free public off-target database.
9. [biorxiv.org/content/10.1101/2025.05.03.652008](https://www.biorxiv.org/content/10.1101/2025.05.03.652008) — CRISMER transformer off-target model (F1=0.7092, PR-AUC=0.8006).
10. [advanced.onlinelibrary.wiley.com/doi/10.1002/advs.202414507](https://advanced.onlinelibrary.wiley.com/doi/10.1002/advs.202414507) — DNA-to-3D face: accuracy + proprietary paired dataset.
11. [academic.oup.com/nar/article/52/D1/D1053/7416388](https://academic.oup.com/nar/article/52/D1/D1053/7416388) — STOmicsDB free spatial transcriptomics hub.
12. [ncbi.nlm.nih.gov/pmc/articles/PMC6586850/](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC6586850/) — Controlled-access genomic data acquisition friction.
