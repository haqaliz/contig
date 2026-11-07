#!/usr/bin/env bash
# Fetch the starter data for docs/planning/research-workbenches/PLAN.md.
#
# Research-use only. Every source is public or free-with-citation; see
# docs/planning/research-workbenches/DATA_SOURCES.md for the license table.
# Large files are resumable; rerunning the script is safe.
set -euo pipefail

cd "$(dirname "$0")/.."
DATA="${DATA:-data}"

get() {
  local url="$1" out="$2"
  mkdir -p "$(dirname "$out")"
  if [[ -s "$out" ]]; then
    echo "skip  $out"
    return
  fi
  echo "fetch $out"
  curl -sSL --fail --retry 3 --retry-delay 3 -C - "$url" -o "$out"
}

# --- M1: variant evidence -----------------------------------------------------
get 'https://ftp.ncbi.nlm.nih.gov/pub/clinvar/vcf_GRCh38/clinvar.vcf.gz' "$DATA/clinvar/clinvar.vcf.gz"
get 'https://ftp.ncbi.nlm.nih.gov/pub/clinvar/vcf_GRCh38/clinvar.vcf.gz.tbi' "$DATA/clinvar/clinvar.vcf.gz.tbi"

get 'https://storage.googleapis.com/public-download-files/hgnc/tsv/tsv/hgnc_complete_set.txt' "$DATA/mane/hgnc_complete_set.txt"
get 'https://ftp.ncbi.nlm.nih.gov/refseq/MANE/MANE_human/release_1.4/MANE.GRCh38.v1.4.summary.txt.gz' "$DATA/mane/MANE.GRCh38.v1.4.summary.txt.gz"

get 'https://civicdb.org/downloads/nightly/nightly-VariantSummaries.tsv' "$DATA/civic/nightly-VariantSummaries.tsv"
get 'https://civicdb.org/downloads/nightly/nightly-civic_accepted.vcf' "$DATA/civic/nightly-civic_accepted.vcf"

# Kaggle: public download endpoint, no account required (verified 2026-11-07).
if [[ ! -s "$DATA/kaggle/clinvar-conflicting/clinvar_conflicting.csv" ]]; then
  get 'https://www.kaggle.com/api/v1/datasets/download/kevinarvai/clinvar-conflicting' "$DATA/kaggle/clinvar-conflicting.zip"
  unzip -oq "$DATA/kaggle/clinvar-conflicting.zip" -d "$DATA/kaggle/clinvar-conflicting"
fi
if [[ ! -s "$DATA/kaggle/gse131027/variants.vcf" ]]; then
  get 'https://www.kaggle.com/api/v1/datasets/download/mannekuntanagendra/variant-calling-human-genome-analysis-gse131027' "$DATA/kaggle/gse131027.zip"
  unzip -oq "$DATA/kaggle/gse131027.zip" -d "$DATA/kaggle/gse131027"
fi

# Ensembl VEP-consequence VCF (catalogue, not a sample call set).
get 'https://ftp.ensembl.org/pub/release-113/variation/vcf/homo_sapiens/homo_sapiens_incl_consequences-chr22.vcf.gz' "$DATA/ensembl/homo_sapiens_incl_consequences-chr22.vcf.gz"
get 'https://ftp.ensembl.org/pub/release-113/variation/vcf/homo_sapiens/homo_sapiens_incl_consequences-chr22.vcf.gz.csi' "$DATA/ensembl/homo_sapiens_incl_consequences-chr22.vcf.gz.csi"

# --- M2/M3: annotation, coverage, panels -------------------------------------
get 'https://ftp.ensembl.org/pub/release-113/gtf/homo_sapiens/Homo_sapiens.GRCh38.113.gtf.gz' "$DATA/ensembl/Homo_sapiens.GRCh38.113.gtf.gz"

get 'https://ftp.clinicalgenome.org/ClinGen_haploinsufficiency_gene_GRCh38.bed' "$DATA/clingen/ClinGen_haploinsufficiency_gene_GRCh38.bed"
get 'https://ftp.clinicalgenome.org/ClinGen_triplosensitivity_gene_GRCh38.bed' "$DATA/clingen/ClinGen_triplosensitivity_gene_GRCh38.bed"
get 'https://hgdownload.soe.ucsc.edu/goldenPath/hg38/database/genomicSuperDups.txt.gz' "$DATA/homology/genomicSuperDups_hg38.txt.gz"

get 'https://raw.githubusercontent.com/nf-core/test-datasets/Sarek/testdata/NA12878_sorted_chrM_chr20_rehead_60pdown.cram' "$DATA/nfcore/NA12878_sorted_chrM_chr20_rehead_60pdown.cram"
get 'https://raw.githubusercontent.com/nf-core/test-datasets/Sarek/testdata/target_chr20.bed' "$DATA/nfcore/target_chr20.bed"
get 'https://raw.githubusercontent.com/nf-core/test-datasets/Sarek/testdata/samplesheet_MT.csv' "$DATA/nfcore/samplesheet_MT.csv"
get 'https://raw.githubusercontent.com/nf-core/test-datasets/Sarek/testdata/grch38_gnomad_reformated_-r3.1.1-.vcf.gz' "$DATA/nfcore/grch38_gnomad_reformated_-r3.1.1-.vcf.gz"

# --- M2/M6: GIAB truth sets ---------------------------------------------------
GIAB='https://ftp-trace.ncbi.nlm.nih.gov/ReferenceSamples/giab/release/AshkenazimTrio'
get "$GIAB/HG002_NA24385_son/v5.0q/HG002_GRCh38_v5.0q_smvar.vcf.gz" "$DATA/giab/HG002_GRCh38_v5.0q_smvar.vcf.gz"
get "$GIAB/HG002_NA24385_son/v5.0q/HG002_GRCh38_v5.0q_smvar.vcf.gz.tbi" "$DATA/giab/HG002_GRCh38_v5.0q_smvar.vcf.gz.tbi"
get "$GIAB/HG002_NA24385_son/v5.0q/HG002_GRCh38_v5.0q_smvar.benchmark.bed" "$DATA/giab/HG002_GRCh38_v5.0q_smvar.benchmark.bed"
for s in HG002_NA24385_son HG003_NA24149_father HG004_NA24143_mother; do
  g="${s%%_*}"
  get "$GIAB/$s/NISTv4.2.1/GRCh38/${g}_GRCh38_1_22_v4.2.1_benchmark.vcf.gz" "$DATA/giab/${g}_GRCh38_1_22_v4.2.1_benchmark.vcf.gz"
  get "$GIAB/$s/NISTv4.2.1/GRCh38/${g}_GRCh38_1_22_v4.2.1_benchmark.vcf.gz.tbi" "$DATA/giab/${g}_GRCh38_1_22_v4.2.1_benchmark.vcf.gz.tbi"
  get "$GIAB/$s/NISTv4.2.1/GRCh38/${g}_GRCh38_1_22_v4.2.1_benchmark_noinconsistent.bed" "$DATA/giab/${g}_GRCh38_1_22_v4.2.1_benchmark_noinconsistent.bed"
done
cat > "$DATA/giab/AshkenazimTrio.ped" <<'PED'
# GIAB Ashkenazim trio. Sex: 1=male, 2=female. Phenotype: -9 unknown.
# Source: https://ftp-trace.ncbi.nlm.nih.gov/ReferenceSamples/giab/release/AshkenazimTrio/
AJtrio	HG002	HG003	HG004	1	-9
AJtrio	HG003	0	0	1	-9
AJtrio	HG004	0	0	2	-9
PED

get 'https://ftp.1000genomes.ebi.ac.uk/vol1/ftp/release/20130502/integrated_call_samples_v3.20130502.ALL.panel' "$DATA/1000g/integrated_call_samples_v3.20130502.ALL.panel"

get 'https://purl.obolibrary.org/obo/hp/hpoa/phenotype.hpoa' "$DATA/hpo/phenotype.hpoa"
get 'https://purl.obolibrary.org/obo/hp/hpoa/genes_to_phenotype.txt' "$DATA/hpo/genes_to_phenotype.txt"

# --- M7: somatic truth sets ---------------------------------------------------
get 'https://storage.googleapis.com/lancet2-paper/truths/COLO829/two-tech_truth/COLO829.TwoTechTruth.final.vcf.gz' "$DATA/lancet2/COLO829.TwoTechTruth.final.vcf.gz"
get 'https://storage.googleapis.com/lancet2-paper/truths/HCC1143/two-tech_truth/HCC1143.TwoTechTruth.final.vcf.gz' "$DATA/lancet2/HCC1143.TwoTechTruth.final.vcf.gz"
get 'https://zenodo.org/api/records/7515830/files/truthset_somaticSVs_COLO829_hg38lifted.vcf/content' "$DATA/lancet2/truthset_somaticSVs_COLO829_hg38lifted.vcf"
get 'https://zenodo.org/api/records/7515830/files/COLO829_somaticSV_copynumber.zip/content' "$DATA/cnv/COLO829_somaticSV_copynumber.zip"
if [[ ! -d "$DATA/cnv/COLO829" ]]; then
  unzip -oq "$DATA/cnv/COLO829_somaticSV_copynumber.zip" -d "$DATA/cnv/COLO829"
fi

MSI='https://raw.githubusercontent.com/mskcc/msisensor/master/test'
for f in example.tumor.bam example.tumor.bam.bai example.normal.bam example.normal.bam.bai example.microsate.sites example.bed msi_score_only_list msi_score_and_status_list run.sh; do
  get "$MSI/$f" "$DATA/msi/$f"
done
get 'https://raw.githubusercontent.com/xjtu-omics/msisensor-pro/master/data/GRCh38.baseline_TCGA-v1.3.tsv' "$DATA/msi/GRCh38.baseline_TCGA-v1.3.tsv"

SEQC2='https://ftp-trace.ncbi.nlm.nih.gov/ReferenceSamples/seqc/Somatic_Mutation_WG/release/latest'
get "$SEQC2/High-Confidence_Regions_v1.2.bed" "$DATA/seqc2/High-Confidence_Regions_v1.2.bed"
get "$SEQC2/high-confidence_sSNV_in_HC_regions_v1.2.1.vcf.gz" "$DATA/seqc2/high-confidence_sSNV_in_HC_regions_v1.2.1.vcf.gz"
get "$SEQC2/high-confidence_sINDEL_in_HC_regions_v1.2.1.vcf.gz" "$DATA/seqc2/high-confidence_sINDEL_in_HC_regions_v1.2.1.vcf.gz"
get "$SEQC2/README.md" "$DATA/seqc2/README.md"

# --- Derived fixtures ---------------------------------------------------------
python3 scripts/build_derived_data.py
python3 scripts/build_trio_subset.py

# --- Persian-specific ---------------------------------------------------------
python3 scripts/fetch_iranome_panel.py --out "$DATA/iranome"

echo "done. run 'python scripts/verify_data.py' to verify and write the manifest."
