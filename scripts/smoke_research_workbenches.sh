#!/usr/bin/env bash
# Manual real-data smoke pass over the research-workbench commands.
# Not run in CI: it needs the downloaded starter data in data/ and samtools.
set -euo pipefail

cd "$(dirname "$0")/.."
OUT="${OUT:-/tmp/contig-research-smoke}"
mkdir -p "$OUT"

echo "== M1 variants (Kaggle sample + ClinVar)"
uv run contig variants data/kaggle/gse131027/variants.vcf \
  --clinvar data/clinvar/clinvar.vcf.gz --build GRCh38 \
  --out "$OUT/variants.tsv"

echo "== M2 readiness (nf-core CRAM + chr20 BED)"
samtools depth -a -b data/nfcore/target_chr20.bed \
  data/nfcore/NA12878_sorted_chrM_chr20_rehead_60pdown.cram > "$OUT/depth.tsv"
uv run contig readiness --depth "$OUT/depth.tsv" \
  --bed data/nfcore/target_chr20.bed \
  --caveats data/homology/homology_caveats_GRCh38.bed \
  --out "$OUT/readiness.tsv"

echo "== M3 panel build (real HGNC + GENCODE, BRCA1/BRCA2)"
uv run contig panel-build --name "BRCA panel" --genes BRCA1,BRCA2 \
  --gtf data/ensembl/Homo_sapiens.GRCh38.113.gtf.gz \
  --hgnc data/mane/hgnc_complete_set.txt \
  --out-dir "$OUT/panels"

echo "== M4 report + M5 ask (fixture run + M1/M2 tables)"
uv run contig report r1 --runs-dir tests/fixtures/reporting/runs \
  --variants tests/fixtures/reporting/variants.json \
  --readiness tests/fixtures/reporting/readiness.json \
  --out "$OUT/report.html" --meta "$OUT/report.json"
uv run contig report-check "$OUT/report.json"
uv run contig ask r1 "is GENE3 ready?" --runs-dir tests/fixtures/reporting/runs \
  --readiness tests/fixtures/reporting/readiness.json

echo "== M6 family (real GIAB trio subset)"
python3 scripts/build_trio_subset.py
uv run contig family --vcf data/giab/AshkenazimTrio_chr20_subset.vcf \
  --ped data/giab/AshkenazimTrio.ped --out "$OUT/family.tsv"

echo "== M7 biomarkers (SEQC2 truth set + callable BED)"
uv run contig biomarkers \
  --vcf data/seqc2/high-confidence_sSNV_in_HC_regions_v1.2.1.vcf.gz \
  --callable-bed data/seqc2/High-Confidence_Regions_v1.2.bed \
  --out "$OUT/biomarkers.tsv"

echo "== M8 local cohort (three M1 fixture tables)"
uv run contig cohort-build --name "smoke" \
  --variants tests/fixtures/cohort/run1.json,tests/fixtures/cohort/run2.json,tests/fixtures/cohort/run3.json \
  --out "$OUT/cohort.json"
uv run contig cohort-query --cohort "$OUT/cohort.json" --gene BRCA1

echo "== done: $OUT"
