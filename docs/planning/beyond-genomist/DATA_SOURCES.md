# Data sources for the Beyond-Genomist milestones

Status: research complete for the first pass; starter data downloaded on
2026-11-07. This is the **data** companion to `PLAN.md`. It answers: for each
milestone, what data exists, where to get it, what it costs, what license it
carries, and what is still missing.

The short version: **we do not need to train a model for M1–M4, M6, or M7.**
The hard part is acquiring and curating the right reference data. Only M5 needs
an LLM, and it is consumed, not trained.

---

## 1. What was actually downloaded

Everything below is in `data/` (gitignored) with a SHA-256 manifest. The refresh
commands are in `scripts/fetch_data.sh` and `scripts/fetch_iranome_panel.py`.

| Milestone | File(s) | Source | License | Size |
|---|---|---|---|---|
| M1 | `clinvar/clinvar.vcf.gz` | NCBI ClinVar FTP | Public domain (US) | 192 MB |
| M1 | `kaggle/clinvar-conflicting/clinvar_conflicting.csv` | Kaggle (kevinarvai) | CC0 | 29 MB |
| M1 | `iranome/iranome_panel.tsv` | Iranome browser (scraped) | Free with citation | 10,613 rows |
| M1 | `civic/nightly-*.tsv`, `nightly-*.vcf` | CIViC | CC0 | 2 MB |
| M1 | `ensembl/homo_sapiens_incl_consequences-chr22.vcf.gz` | Ensembl VEP consequences | Open (Ensembl) | 256 MB |
| M1/M3 | `mane/MANE.GRCh38.v1.4.summary.txt.gz` | NCBI MANE | Public | 1.1 MB |
| M1/M3 | `mane/hgnc_complete_set.txt` | HGNC | Free with attribution | 17 MB |
| M1/M6 | `kaggle/gse131027/variants.vcf` | Kaggle (GSE131027) | MIT | 4 MB |
| M2 | `ensembl/Homo_sapiens.GRCh38.113.gtf.gz` | Ensembl/GENCODE | Open | 61 MB |
| M2 | `clingen/ClinGen_*_GRCh38.bed` | ClinGen | CC0 | 89 KB |
| M2 | `nfcore/NA12878_*.cram`, `target_chr20.bed` | nf-core/test-datasets (Sarek) | MIT | 22 MB |
| M2/M6 | `giab/HG00{2,3,4}_*.vcf.gz`, `*.bed` | GIAB/NIST | Public | ~450 MB |
| M2/M3 | `panels_iranome_genes_GRCh38.bed` | Built here from GENCODE | Derived; GENCODE terms | 322 exons |
| M6 | `giab/AshkenazimTrio.ped` | GIAB relationships | Public metadata | 3 rows |
| M6 | `hpo/phenotype.hpoa`, `genes_to_phenotype.txt` | HPO | HPO license; cite | 54 MB |
| M6 | `1000g/integrated_call_samples_v3.20130502.ALL.panel` | 1000 Genomes/IGSR | Open | 55 KB |
| M7 | `lancet2/COLO829.TwoTechTruth.final.vcf.gz` | Lancet2 public GCS | Public; cite | 1.9 MB |
| M7 | `lancet2/HCC1143.TwoTechTruth.final.vcf.gz` | Lancet2 public GCS | Public; cite | 1.1 MB |
| M7 | `lancet2/truthset_somaticSVs_COLO829_hg38lifted.vcf` | Zenodo 7515830 | CC BY 4.0 | 81 KB |
| M7 | `seqc2/high-confidence_s{SNV,INDEL}_in_HC_regions_v1.2.1.vcf.gz` | NCBI SEQC2 FTP | Public; cite SEQC2 | 4.9 MB |
| M7 | `seqc2/High-Confidence_Regions_v1.2.bed` | NCBI SEQC2 FTP | Public; cite SEQC2 | 16 MB |

The manifest (`data/manifest.json`) records the exact URL, byte size, and SHA-256
for each file.

---

## 2. The open data landscape (deep dive)

### 2.1 ClinVar — the clinical assertion backbone

- **What:** 4.6M variant records with clinical significance, condition, review
  status, and submitter evidence. This is the closest open equivalent to the
  clinical interpretation layer Genomist sells.
- **Where:** `https://ftp.ncbi.nlm.nih.gov/pub/clinvar/vcf_GRCh38/` (VCF),
  `/xml/` (full submissions), `/tab_delimited/` (summary tables).
- **License:** ClinVar is a work of the US Government and is in the public domain
  in the US. It aggregates third-party submissions; check the submitter terms for
  commercial redistribution of the full submission set.
- **Use for Contig:** display "ClinVar reports X" with the ClinVar release date
  and review status. Never restate it as Contig's own classification.
- **Gotcha:** the VCF is a **variant catalogue**, not a sample call set. Do not
  use it as a truth set for a sample; join it to the run's calls.

### 2.2 gnomAD — population frequency

- **What:** allele frequencies and constraint metrics from >800k exomes/genomes.
- **Where:** `https://gnomad.broadinstitute.org/downloads` (bulk VCFs) and
  `https://gnomad.broadinstitute.org/api` (GraphQL, per-variant queries).
- **License:** **CC0** (verified via gnomAD terms). Bulk downloads are free.
- **Use for Contig:** a frequency column and a rare-variant filter. Do **not**
  download the full VCF set for a starter environment; query the API with a local
  cache, or use a per-chromosome subset.
- **Gotcha:** the full v4 sites VCFs are hundreds of GB. The API returns one
  variant at a time; batch thoughtfully and cache.

### 2.3 GIAB — truth sets and trio data

- **What:** high-confidence small-variant and structural-variant truth sets for
  HG001–HG007, including the Ashkenazim trio (HG002 son, HG003 father, HG004
  mother) and the Chinese trio (HG005/6/7).
- **Where:** `https://ftp-trace.ncbi.nlm.nih.gov/ReferenceSamples/giab/release/`
  (the `latest`, `v5.0q`, and `NISTv4.2.1` directories).
- **License:** public NIST/GIAB data; cite the GIAB consortium.
- **Use for Contig:** M2 coverage truth, M6 Mendelian consistency and sample-swap
  tests, M7 normalization. HG002 v5.0q is the current small-variant benchmark;
  v4.2.1 is the convenient trio set (all three members have matching VCFs and
  no-inconsistent BEDs).
- **Gotcha:** v5.0q is HG002-only. For a trio, use v4.2.1 for all three, or mix
  versions only with a documented caveat.

### 2.4 1000 Genomes / IGSR — diversity and sample metadata

- **What:** 2,504 samples from 26 populations, phased VCFs, sample panel.
- **Where:** `https://ftp.1000genomes.ebi.ac.uk/vol1/ftp/release/20130502/`
  (phase 3, GRCh37) and the 30x GRCh38 collection.
- **License:** open, freely available; cite IGSR/1000 Genomes.
- **Use for Contig:** population context, cohort tests, and a source of
  non-European alleles. The sample panel (downloaded) is enough for metadata;
  download one chromosome only if a test needs calls.
- **Gotcha:** phase 3 is GRCh37; the 30x collection is GRCh38. Do not mix builds
  without liftover.

### 2.5 Iranome — the Iranian allele-frequency resource

- **What:** whole-exome data from 1,200 Iranians across 12 ethnic groups (Arabs,
  Azeris, Balochs, Gilakis, Kurds, Lurs, Mazanis, Persians, Persian Gulf
  Islanders, Sistanis, Turkmen, Zartoshtis). 1.5M variants, 37k with AF >1%.
- **Where:** `https://www.iranome.com/` (browser). There is **no bulk download
  endpoint**; the site exposes per-gene/per-region/per-variant pages that embed
  the variant array in `window.table_variants`.
- **License:** the site's terms say: *"The data presented here can be used freely
  and we just request that you cite the Iranome database as the data source."*
  Cite Fattahi et al., Hum Mutat 2019;40(11):1968–1984.
- **Use for Contig:** a Persian-specific frequency column and a strong local
  differentiator. `scripts/fetch_iranome_panel.py` pulls 16 clinically relevant
  genes into `data/iranome/iranome_panel.tsv` (10,613 variants).
- **Gotcha:** GRCh37 (`Human_g1k_v37_decoy`), Ensembl 75, dbSNP 155. It must be
  lifted over before joining to GRCh38 calls. The browser data is aggregated;
  do not infer individual genotypes.

### 2.6 GME Variome, al mena, Qatar, Emirati, TCGS, PERSIAN

These are the other Middle East / Iranian resources worth knowing:

| Resource | What | Access status (2026-11-07) | Use |
|---|---|---|---|
| **GME Variome** | 1,111 exomes from the Greater Middle East | The documented download URL (`http://igm.ucsd.edu/gme/download.shtml`) is **404**; the project page is gone. Some mirrors/derived tables exist (Nirvana docs, papers). | Fallback: Iranome + gnomAD Middle East. Treat as unavailable until a mirror is found. |
| **al mena** | 26M variants from Arab/Middle East/North Africa | Site `clingen.igib.res.in/almena/` did not respond during this check. | Fallback: Iranome + gnomAD. |
| **Qatar Genome (QGP)** | Population-specific allele frequencies; QGP variant browser | Portal/registration; no open bulk download verified. | Request access if the Qatari market matters. |
| **Emirati Genome Project** | 43,608 WGS allele frequencies | EGA study `EGAS50000001071`; controlled access. | Request access; not for the first build. |
| **TCGS (Tehran Cardiometabolic Genetic Study)** | ~20k participants, family-based cohort | Contact study team; not public due to participant privacy. | Potential Iranian cohort collaboration; not a data download. |
| **PERSIAN Cohort** | 18-region adult cohort + biobank | Concept submission via `persiancohort.com/site/access`. | Potential collaboration; not open data. |

**Conclusion:** Iranome is the only freely usable Iranian frequency resource for
the first pass. GME and al mena are effectively unavailable right now. Qatar,
Emirati, TCGS, and PERSIAN are relationship/application plays, not downloads.

### 2.7 Cancer variant evidence

- **CIViC** (`https://civicdb.org/`): CC0, nightly TSV/VCF. Downloaded. Use it as
  attributed cancer evidence, not as a prescribing guide.
- **ClinGen** (`https://search.clinicalgenome.org/kb/downloads`): CC0 dosage
  sensitivity BEDs. Downloaded. Use for CNV/haploinsufficiency caveats.
- **ClinVar**: also covers cancer assertions; downloaded.
- **OncoKB**: free for research/academic but a commercial license is required for
  commercial use. **Do not embed.**
- **COSMIC**: free for academic/non-commercial; commercial license required.
  **Do not embed.**
- **HGMD**: licensed. **Do not embed.**
- **NCCN**: licensed guidelines. **Do not embed or paraphrase.**
- **TCGA / cBioPortal**: open processed data for research; raw controlled-access
  data needs dbGaP. Use cBioPortal for cohort demos, not for clinical claims.
- **SEQC2**: public high-confidence somatic truth set on the NCBI FTP at
  `https://ftp-trace.ncbi.nlm.nih.gov/ReferenceSamples/seqc/Somatic_Mutation_WG/release/latest/`.
  Downloaded (SNV/INDEL VCFs + high-confidence BED).
- **Lancet2 truth sets**: public GCS at
  `gs://lancet2-paper/truths/<cell line>/two-tech_truth/`. COLO829 and HCC1143
  downloaded.
- **COLO829 SV truth set**: Zenodo 7515830, CC BY 4.0. Downloaded.

### 2.8 Annotation and transcript resources

- **GENCODE** (`https://www.gencodegenes.org/human/`): open, comprehensive gene
  annotation. Downloaded (Ensembl 113 GTF).
- **MANE Select** (`https://www.ncbi.nlm.nih.gov/refseq/MANE/`): public; one
  representative transcript per gene. Downloaded.
- **HGNC** (`https://www.genenames.org/download/`): approved symbols and aliases;
  free with attribution. Downloaded (17 MB).
- **Ensembl VEP consequences** (`https://ftp.ensembl.org/pub/release-113/variation/vcf/homo_sapiens/`):
  the `homo_sapiens_incl_consequences-chr22.vcf.gz` file is a real VEP-annotated
  VCF; downloaded. Use it to test CSQ parsing and the M1 evidence table.
- **ClinGen dosage sensitivity**: downloaded.
- **UCSC segmental duplications / RepeatMasker**: for M2 homology and pseudogene
  caveats. Not downloaded; query UCSC or download the tracks.
- **Reference FASTA (GRCh38)**: ~1 GB; use iGenomes/Ensembl at run time. Not
  downloaded to keep the starter set small.

### 2.9 Population and phenotype context

- **HPO** (`https://hpo.jax.org/`): phenotype ontology and gene–disease
  annotations; custom license, free with citation (confirm commercial terms
  before shipping). Downloaded.
- **HPO annotations**: `phenotype.hpoa` and `genes_to_phenotype.txt`; downloaded.
- **OMIM**: licensed; do not embed. Use HPO/ClinVar/GeneReviews (free) as the
  open path.
- **GeneReviews / NCBI Bookshelf**: free; useful for narrative context but do not
  copy text into a commercial report without checking terms.

---

## 3. Kaggle and Hugging Face: what is actually useful

### Kaggle

Kaggle is **not** a primary source for raw genomics data. Most "genomics"
datasets are derived tables, not VCFs. Two are genuinely useful:

| Dataset | What | License | Size | Verdict |
|---|---|---|---|---|
| `kevinarvai/clinvar-conflicting` | ClinVar variant table with consequence, CADD, SIFT, PolyPhen, clinical significance | **CC0** | 3.7 MB zip / 29 MB CSV | Good for M1 UI and classification tests |
| `mannekuntanagendra/variant-calling-human-genome-analysis-gse131027` | A sample `variants.vcf` plus FastQC reports | **MIT** | 1.3 MB zip / 4 MB VCF | Good small VCF fixture; not a truth set |

How to fetch without an account:

```bash
curl -L 'https://www.kaggle.com/api/v1/datasets/download/kevinarvai/clinvar-conflicting' -o clinvar.zip
```

(The public download endpoint worked without credentials during this check.
Respect Kaggle's terms and the dataset licenses.)

**Do not use Kaggle as the source of record.** Use it for convenience fixtures;
the primary sources (NCBI, EBI, GIAB, CIViC, Iranome) are more current and have
clearer provenance.

### Hugging Face

`hf datasets list --search genomics` works, but the results are mostly ML
datasets, not raw VCFs. Relevant examples:

| Dataset | What | License | Verdict |
|---|---|---|---|
| `songlab/clinvar` | ClinVar-derived variant effect dataset | MIT | Useful for ML experiments, not a clinical evidence source |
| `songlab/gnomad` | gnomAD-derived variant dataset | MIT | Same |
| `InstaDeepAI/genomics-long-range-benchmark` | Genomics benchmark | CC BY-NC-SA 4.0 | Non-commercial; benchmark only |
| `microsoft/msr_genomics_kbcomp` | Genomics knowledge-base completion | Other | NLP, not variant data |

**Conclusion:** Hugging Face is useful for model/eval datasets, not for primary
variant data. Do not build the clinical evidence layer on it.

---

## 4. Licensing: what you can ship and what you cannot

| Resource | License | Can we ship it in a commercial product? |
|---|---|---|
| ClinVar | Public domain (US) | Yes, with attribution and submitter caveats |
| gnomAD | CC0 | Yes |
| GIAB / NIST | Public | Yes |
| 1000 Genomes / IGSR | Open | Yes, with citation |
| Iranome | Free with citation | Yes, with citation; check redistribution wording |
| GME / al mena | Unclear / unavailable | Not until terms are confirmed |
| CIViC | CC0 | Yes |
| ClinGen | CC0 | Yes, with attribution |
| HPO | Custom HPO license | Likely yes with citation; confirm commercial terms |
| GENCODE / Ensembl | Open | Yes, with attribution |
| MANE / RefSeq | Public | Yes |
| HGNC | Free with attribution | Yes, with attribution |
| nf-core test data | MIT | Yes |
| Lancet2 truth sets | Public paper data | Research use; cite; confirm redistribution |
| COLO829 SV truth set | CC BY 4.0 | Yes, with attribution |
| SEQC2 | Public | Yes, with attribution; check the paper/terms |
| **OMIM** | Proprietary | **No** without a license |
| **NCCN** | Proprietary | **No** without a license |
| **COSMIC** | Free academic; commercial license | **No** for commercial without a license |
| **HGMD** | Proprietary | **No** |
| **OncoKB** | Free research; commercial license | **No** for commercial without a license |
| **dbNSFP (academic)** | CC BY-NC-ND 4.0 | **No** for commercial |
| **CADD** | Non-commercial | **No** for commercial |
| **REVEL** | Non-commercial | **No** for commercial |
| **SpliceAI** | CC BY-NC 4.0 | **No** for commercial |
| **AlphaMissense predictions** | CC BY 4.0 (per DeepMind) | Yes, with attribution; confirm the exact redistribution terms |

**Recommended policy for the first pass:** ship only the open path (ClinVar,
gnomAD, GIAB, 1000G, Iranome, CIViC, ClinGen, HPO, GENCODE, MANE, HGNC). Use
non-commercial scores (dbNSFP/CADD/REVEL/SpliceAI) only in development and
evaluation, behind a flag, and never in a commercial build. If a score column is
essential, license it or use AlphaMissense (CC BY 4.0).

---

## 5. Milestone mapping: what we have, what is missing

### M1 — Variant workbench

**Have:** ClinVar VCF and Kaggle ClinVar table, Iranome panel, CIViC, Ensembl
VEP-annotated chr22, MANE, HGNC, a small sample VCF, gnomAD subset.

**Missing:**
- A **real sample VCF annotated with VEP/SnpEff** from a Contig run or a design
  partner. The Ensembl chr22 file is a catalogue, not a sample.
- A gnomAD API client + cache (do not bulk-download).
- A decision on optional score columns and their licenses.
- A design partner to say which filters matter.

**Model:** none.

### M2 — Coverage and interpretation readiness

**Have:** GENCODE GTF, MANE, ClinGen dosage BED, GIAB high-confidence BED,
nf-core CRAM + target BED, HGNC, a generated exon BED.

**Missing:**
- GRCh38 FASTA + `.fai` at run time (iGenomes/Ensembl).
- Homology/pseudogene region list (UCSC segmental duplications, RepeatMasker).
- Real coverage outputs from sarek/RNA-seq to decide compute-vs-consume.
- A small BAM/CRAM fixture with known depths (the nf-core CRAM is a start).

**Model:** none.

### M3 — Panel builder and registry

**Have:** HGNC, GENCODE, MANE, a 16-gene exon BED, ClinGen dosage.

**Missing:**
- A real lab panel BED or two (Twist/Agilent are licensed; use GENCODE-derived
  panels or a design partner's panel).
- A decision on 0-based vs 1-based, BED vs interval list, transcript-level vs
  gene-level.
- A panel validation fixture set (wrong contig, empty overlap, duplicate genes).

**Model:** none.

### M4 — Report builder

**Have:** Contig run bundles and the existing HTML report.

**Missing:**
- 2–3 real report examples from target users (publication, core facility,
  internal review).
- A decision on PDF tooling and template format.
- A reviewer/sign-off workflow definition.

**Model:** none.

### M5 — Ask-your-run assistant

**Have:** Contig run bundles.

**Missing:**
- A 30–50 question eval set with expected cited sources, built from real and
  synthetic bundles.
- An adversarial set (prompt injection in logs, misleading report text, missing
  data).
- A model/provider decision with privacy terms; a local-model option for
  air-gapped labs.
- A cost/latency budget.

**Model:** yes — an LLM, hosted or local. **No training required initially.**

### M6 — Family analysis

**Have:** GIAB trio VCFs, PED, no-inconsistent BEDs, HPO, 1000G panel.

**Missing:**
- A decision on pedigree format and sample-sheet mapping.
- A relatedness method (KING-style vs. simpler genotype concordance).
- A carrier panel definition (ACMG SF or a curated list).
- A real trio VCF from a design partner (GIAB is a good truth set but not a
  product-shaped family).

**Model:** none.

### M7 — Oncology biomarker verification

**Have:** Lancet2 COLO829/HCC1143 small-variant truth sets, COLO829 SV truth set,
SEQC2 high-confidence SNV/INDEL truth set + high-confidence regions, CIViC,
ClinVar, ClinGen.

**Missing:**
- MSI/TMB reference data: HCT116 (MSI-H) and an MSS control (SW480/COLO829),
  from SRA/CCLE or a public benchmark.
- A real tumor-normal and tumor-only run with the pipeline's MSI/TMB/LOH/CNV
  outputs.
- A domain reviewer to set honest sanity bands.
- Licensing review for any cancer evidence source.

**Model:** none.

### M8 — Cohort / federated frequency

**Have:** nothing yet.

**Missing:** demand from at least two labs, a consent/IRB posture, a privacy
method (k-anonymity or differential privacy), and a tenancy/audit design. Do not
build this before M1–M4 have users.

**Model:** none.

---

## 6. Acquisition backlog (next steps, in order)

1. **gnomAD API client + cache** (M1). No bulk download; test the GraphQL API
   with a handful of variants and cache results locally.
2. **Homology/pseudogene BED** (M2). UCSC segmental duplications + a curated
   SMN1/SMN2 and PMS2/PMS2CL list.
3. **GRCh38 FASTA + `.fai`** (M2). Use iGenomes or Ensembl; do not commit.
4. **SEQC2 truth set** (M7). **Done** — high-confidence SNV/INDEL VCFs and BED
   downloaded from the NCBI FTP.
5. **MSI/TMB reference data** (M7). HCT116 (MSI-H) + MSS control from SRA/CCLE.
6. **A real annotated VCF** (M1). Request from a design partner or generate one
   with a sarek run on the GIAB sample.
7. **A real trio VCF** (M6). Request from a design partner; GIAB stays the truth
   set.
8. **A lab panel BED** (M3). Request one; otherwise use the GENCODE-derived
   panel.
9. **Report examples** (M4). Ask two target users for a redacted report.
10. **License confirmation** (M1/M6). HPO and HGNC commercial terms; decide on
    dbNSFP/CADD/REVEL/SpliceAI or use AlphaMissense.

---

## 7. Reproducibility

```bash
# Public downloads (resumable, idempotent)
bash scripts/fetch_data.sh

# Iranome per-gene scrape (respects the site: 1 request/second)
python scripts/fetch_iranome_panel.py

# Verify everything
python scripts/verify_data.py
```

`data/manifest.json` is the source of record for what was downloaded, from where,
under which license, and with which SHA-256.
