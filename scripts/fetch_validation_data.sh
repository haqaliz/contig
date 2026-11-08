#!/bin/bash
# Fetch only the small, open validation artifacts. Large BAMs are deliberately
# not downloaded; the script prints their routes instead.
#
# Usage: bash scripts/fetch_validation_data.sh [data-dir] [target]
# Targets: all (default), panelapp, ascat, giab, seqc2, msi
set -euo pipefail

DATA_DIR="${1:-data}"
TARGET="${2:-all}"
DATA_DIR="$(mkdir -p "$DATA_DIR" && cd "$DATA_DIR" && pwd)"

fetch_panelapp() {
  local dir="$DATA_DIR/panelapp"
  mkdir -p "$dir"
  if [ ! -f "$dir/panel-245.json" ]; then
    echo "Fetching PanelApp panel 245 (small JSON)"
    curl -fsSL --max-time 60 \
      'https://panelapp.genomicsengland.co.uk/api/v1/panels/245/' \
      -o "$dir/panel-245.json"
  fi
  python3 - "$dir/panel-245.json" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
genes = [g["gene_data"]["gene_symbol"] for g in d["genes"]
         if g["entity_type"] == "gene" and g["confidence_level"] == "3"]
open(sys.argv[1].replace(".json", "_green_genes.txt"), "w").write(",".join(genes))
print(f"PanelApp {d['name']} v{d['version']}: {len(genes)} green genes")
PY
}

fetch_ascat() {
  local dir="$DATA_DIR/cnv/tcga_ascat"
  mkdir -p "$dir"
  local file="$dir/TCGA-COAD.ascat2.allelic_specific.seg.txt"
  if [ ! -f "$file" ]; then
    echo "Fetching one open TCGA-COAD ASCAT allele-specific segment file (small)"
    curl -fsSL --max-time 60 \
      'https://api.gdc.cancer.gov/data/9e47f23f-1a3d-495f-bb73-c600728898dc' \
      -o "$file"
  fi
  echo "ASCAT columns: $(head -1 "$file")"
  echo "ASCAT file: $file ($(wc -l < "$file") lines)"
}

check_giab() {
  echo "GIAB Ashkenazim trio (open; already local if these exist):"
  for f in \
    "$DATA_DIR/giab/HG002_GRCh38_1_22_v4.2.1_benchmark.vcf.gz" \
    "$DATA_DIR/giab/HG003_GRCh38_1_22_v4.2.1_benchmark.vcf.gz" \
    "$DATA_DIR/giab/HG004_GRCh38_1_22_v4.2.1_benchmark.vcf.gz" \
    "$DATA_DIR/giab/AshkenazimTrio_chr20_subset.vcf" \
    "$DATA_DIR/giab/AshkenazimTrio.ped"; do
    if [ -f "$f" ]; then echo "  present: $f"; else echo "  missing: $f"; fi
  done
  echo "  source: https://ftp-trace.ncbi.nlm.nih.gov/ReferenceSamples/giab/release/AshkenazimTrio/"
}

check_seqc2() {
  echo "SEQC2 HCC1395 truth set (open; already local if these exist):"
  for f in \
    "$DATA_DIR/seqc2/high-confidence_sSNV_in_HC_regions_v1.2.1.vcf.gz" \
    "$DATA_DIR/seqc2/high-confidence_sINDEL_in_HC_regions_v1.2.1.vcf.gz" \
    "$DATA_DIR/seqc2/High-Confidence_Regions_v1.2.bed"; do
    if [ -f "$f" ]; then echo "  present: $f"; else echo "  missing: $f"; fi
  done
  echo "  source: https://ftp-trace.ncbi.nlm.nih.gov/ReferenceSamples/seqc/Somatic_Mutation_WG/release/latest/"
  echo "  BAMs:   https://ftp-trace.ncbi.nlm.nih.gov/ReferenceSamples/seqc/Somatic_Mutation_WG/data/WGS/ (large)"
}

check_msi() {
  echo "MSI tumor/normal validation:"
  echo "  paired BAMs with known MSI status are controlled access (TCGA/CPTAC via dbGaP/EGA)."
  echo "  start: https://dbgap.ncbi.nlm.nih.gov/ or https://ega-archive.org/"
  echo "  open cell-line fallback (tumor-only, no matched normal):"
  echo "    HCT116 WGS SRR8639145; HCT116 targeted-capture SRR8657432"
  echo "    SW480 targeted-capture SRR8657564"
  echo "  known status: HCT116 MSI-H; SW480 MSS (Cellosaurus / Cell Model Passports)."
  echo "  do not present a cell-line-only run as the paired MSI validation."
}

case "$TARGET" in
  all) fetch_panelapp; fetch_ascat; check_giab; check_seqc2; check_msi ;;
  panelapp) fetch_panelapp ;;
  ascat) fetch_ascat ;;
  giab) check_giab ;;
  seqc2) check_seqc2 ;;
  msi) check_msi ;;
  *) echo "unknown target: $TARGET" >&2; exit 2 ;;
esac
