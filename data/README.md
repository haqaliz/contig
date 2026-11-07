# Starter data for the research-workbench milestones

This directory holds **downloaded, research-use data** for M1–M7 of
`docs/planning/research-workbenches/PLAN.md`. It is not part of the shipped package
and should not be committed (see `.gitignore`). The inventory, licenses, and
source URLs are in `docs/planning/research-workbenches/DATA_SOURCES.md`.

Refresh with:

```bash
bash scripts/fetch_data.sh          # public downloads (idempotent, resumable)
python scripts/fetch_iranome_panel.py

# Manual real-data smoke across all eight commands (needs samtools/tabix)
OUT=/tmp/contig-research-smoke bash scripts/smoke_research_workbenches.sh
```

## What is here

| Path | What it is | Records / size | License |
|---|---|---|---|
| `clinvar/clinvar.vcf.gz` | ClinVar GRCh38 VCF (clinical assertions) + index | 4.6M records, 192 MB | Public domain (NCBI) |
| `giab/HG002_GRCh38_v5.0q_smvar.vcf.gz` | GIAB HG002 small-variant truth set (v5.0q) + index | 5.9M records, 40 MB | Public (NIST/GIAB) |
| `giab/HG00{2,3,4}_GRCh38_1_22_v4.2.1_benchmark.vcf.gz` | GIAB Ashkenazim trio truth sets (v4.2.1) | ~140 MB each | Public (NIST/GIAB) |
| `giab/*.bed` | GIAB high-confidence regions and no-inconsistent regions | 0.7–13 MB | Public (NIST/GIAB) |
| `giab/AshkenazimTrio.ped` | Pedigree for HG002/HG003/HG004 | 3 rows | Public metadata |
| `iranome/iranome_panel.tsv` | Iranian allele frequencies for 16 genes, scraped from Iranome | 10,613 rows | Free use with citation (Iranome) |
| `iranome/raw/*.json` | Raw Iranome JSON per gene | ~40 MB | Free use with citation |
| `kaggle/clinvar-conflicting/clinvar_conflicting.csv` | Kaggle ClinVar conflicting-classifications table | 65,188 rows, 29 MB | CC0 |
| `kaggle/gse131027/variants.vcf` | Kaggle variant-calling output (GSE131027) | 32,685 records, 4 MB | MIT |
| `lancet2/COLO829.TwoTechTruth.final.vcf.gz` | COLO829 somatic small-variant truth set | 1.9 MB | Public (Lancet2 paper; cite) |
| `lancet2/HCC1143.TwoTechTruth.final.vcf.gz` | HCC1143 somatic small-variant truth set | 1.1 MB | Public (Lancet2 paper; cite) |
| `lancet2/truthset_somaticSVs_COLO829_hg38lifted.vcf` | COLO829 somatic SV truth set (GRCh38) | 81 KB | CC BY 4.0 (Zenodo) |
| `seqc2/high-confidence_s{SNV,INDEL}_in_HC_regions_v1.2.1.vcf.gz` | SEQC2 high-confidence somatic truth set | 4.6 MB + 263 KB | Public; cite SEQC2 |
| `seqc2/High-Confidence_Regions_v1.2.bed` | SEQC2 high-confidence regions | 16 MB | Public; cite SEQC2 |
| `msi/example.tumor.bam` + `example.normal.bam` | MSIsensor tumor/normal example BAMs | 44 MB | Public example data; cite MSIsensor |
| `msi/example.microsate.sites` | MSIsensor microsatellite sites | 238 B | Public example data |
| `msi/msi_score_and_status_list` | MSIsensor example score/status distribution | 1.1 KB | Public example data |
| `msi/GRCh38.baseline_TCGA-v1.3.tsv` | MSIsensor TCGA baseline sites | 869 KB | Public; cite MSIsensor |
| `cnv/COLO829/copynumber/*` | COLO829 copy-number segments | 2.9k rows | CC BY 4.0 (Zenodo) |
| `giab/AshkenazimTrio_chr20_subset.vcf` | Real multi-sample GIAB trio subset (chr20) | 399 ALT rows | Public (NIST/GIAB) |
| `civic/nightly-VariantSummaries.tsv` | CIViC cancer variant summaries | 585 KB | CC0 |
| `civic/nightly-civic_accepted.vcf` | CIViC accepted cancer variants | 1.4 MB | CC0 |
| `clingen/ClinGen_haploinsufficiency_gene_GRCh38.bed` | ClinGen dosage sensitivity (haploinsufficiency) | 48 KB | CC0 |
| `clingen/ClinGen_triplosensitivity_gene_GRCh38.bed` | ClinGen dosage sensitivity (triplosensitivity) | 41 KB | CC0 |
| `homology/genomicSuperDups_hg38.txt.gz` | UCSC segmental duplications (homology caveats) | 4 MB | Open (UCSC) |
| `homology/homology_caveats_GRCh38.bed` | Curated SMN1/SMN2, PMS2/PMS2CL, HBA1/HBA2 exon BED | 1,105 exon rows | Derived from GENCODE |
| `hpo/phenotype.hpoa` | HPO disease–phenotype annotations | 34 MB | HPO license; cite |
| `hpo/genes_to_phenotype.txt` | HPO gene–phenotype annotations | 20 MB | HPO license; cite |
| `mane/MANE.GRCh38.v1.4.summary.txt.gz` | MANE Select transcript summary | 1.1 MB | Public (NCBI) |
| `mane/hgnc_complete_set.txt` | HGNC gene symbols and aliases | 17 MB | HGNC terms; cite |
| `ensembl/Homo_sapiens.GRCh38.113.gtf.gz` | GENCODE/Ensembl gene annotation | 61 MB | Open (Ensembl/GENCODE) |
| `ensembl/homo_sapiens_incl_consequences-chr22.vcf.gz` | Ensembl VEP-consequence-annotated chr22 VCF | 256 MB | Open (Ensembl) |
| `nfcore/NA12878_sorted_chrM_chr20_rehead_60pdown.cram` | nf-core/sarek test CRAM (chr20/chrM) | 22 MB | MIT |
| `nfcore/target_chr20.bed` | nf-core/sarek chr20 target BED | 4 KB | MIT |
| `nfcore/grch38_gnomad_reformated_-r3.1.1-.vcf.gz` | Tiny gnomAD subset (chr20:90000–92000) | 366 records | MIT project data; gnomAD CC0 |
| `1000g/integrated_call_samples_v3.20130502.ALL.panel` | 1000 Genomes sample/population panel | 2,504 samples | Open (IGSR) |
| `panels_iranome_genes_GRCh38.bed` | Exon BED for the 16 Iranome genes, built from GENCODE | 322 exons | Derived; GENCODE terms |

## What is deliberately not here

- **Full gnomAD VCFs.** Too large for a starter set; use the gnomAD GraphQL API
  or a per-chromosome subset.
- **Reference FASTA.** GRCh38 is ~1 GB; use iGenomes/Ensembl at run time.
- **SEQC2 somatic truth set.** Public but Google Drive–hosted; see the data
  sources doc for links.
- **OMIM, NCCN, COSMIC, HGMD, OncoKB.** Licensed content; do not embed without a
  commercial license. Use ClinVar/CIViC/ClinGen for the open path.
- **dbNSFP, CADD, REVEL, SpliceAI.** Non-commercial-only; see the licensing
  table in the data sources doc before shipping any score column.

## Provenance

Every file was fetched on 2026-11-07. `data/manifest.json` records the source URL,
license, size, and SHA-256 for each file. Re-check upstream versions before a
release; these are moving resources.
