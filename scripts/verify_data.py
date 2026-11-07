#!/usr/bin/env python3
"""Verify the downloaded starter data and write data/manifest.json.

Checks gzip integrity where applicable, counts VCF records, and records the
SHA-256 of every file. Research-use data only; see DATA_SOURCES.md.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"

# path prefix -> (source_url, license, milestone, note)
META: dict[str, tuple[str, str, str, str]] = {
    "clinvar/": ("https://ftp.ncbi.nlm.nih.gov/pub/clinvar/vcf_GRCh38/", "Public domain (US)", "M1", "ClinVar GRCh38 VCF"),
    "civic/": ("https://civicdb.org/releases", "CC0", "M1/M7", "CIViC nightly release"),
    "clingen/": ("https://search.clinicalgenome.org/kb/downloads", "CC0", "M2/M7", "ClinGen dosage sensitivity"),
    "hpo/": ("https://purl.obolibrary.org/obo/hp/hpoa/", "HPO license; cite", "M6", "HPO annotations"),
    "mane/MANE": ("https://ftp.ncbi.nlm.nih.gov/refseq/MANE/", "Public (NCBI)", "M1/M3", "MANE Select summary"),
    "mane/hgnc": ("https://www.genenames.org/download/", "Free with attribution", "M1/M3", "HGNC complete set"),
    "ensembl/Homo_sapiens": ("https://ftp.ensembl.org/pub/release-113/gtf/homo_sapiens/", "Open (Ensembl/GENCODE)", "M2", "GENCODE/Ensembl GTF"),
    "ensembl/homo_sapiens_incl_consequences": ("https://ftp.ensembl.org/pub/release-113/variation/vcf/homo_sapiens/", "Open (Ensembl)", "M1", "VEP-consequence VCF (catalogue, not a sample)"),
    "giab/": ("https://ftp-trace.ncbi.nlm.nih.gov/ReferenceSamples/giab/release/AshkenazimTrio/", "Public (NIST/GIAB)", "M2/M6", "GIAB truth set"),
    "homology/genomicSuperDups": ("https://hgdownload.soe.ucsc.edu/goldenPath/hg38/database/genomicSuperDups.txt.gz", "Open (UCSC)", "M2", "Segmental duplications"),
    "homology/homology_caveats": ("Derived from GENCODE GRCh38.113", "Derived; GENCODE terms", "M2", "SMN1/SMN2, PMS2/PMS2CL, HBA1/HBA2 caveat BED"),
    "iranome/": ("https://www.iranome.com/", "Free with citation (Iranome)", "M1", "Iranian allele frequencies; cite Fattahi 2019"),
    "kaggle/clinvar-conflicting/": ("https://www.kaggle.com/datasets/kevinarvai/clinvar-conflicting", "CC0", "M1", "Kaggle ClinVar table"),
    "kaggle/gse131027/": ("https://www.kaggle.com/datasets/mannekuntanagendra/variant-calling-human-genome-analysis-gse131027", "MIT", "M1", "Small sample VCF fixture"),
    "lancet2/COLO829.TwoTechTruth": ("https://storage.googleapis.com/lancet2-paper/truths/COLO829/", "Public; cite Lancet2", "M7", "COLO829 somatic small-variant truth set"),
    "lancet2/HCC1143.TwoTechTruth": ("https://storage.googleapis.com/lancet2-paper/truths/HCC1143/", "Public; cite Lancet2", "M7", "HCC1143 somatic small-variant truth set"),
    "lancet2/truthset_somaticSVs": ("https://zenodo.org/records/7515830", "CC BY 4.0", "M7", "COLO829 somatic SV truth set"),
    "nfcore/": ("https://github.com/nf-core/test-datasets/tree/Sarek/testdata", "MIT", "M2", "nf-core/sarek test data"),
    "seqc2/": ("https://ftp-trace.ncbi.nlm.nih.gov/ReferenceSamples/seqc/Somatic_Mutation_WG/release/latest/", "Public; cite SEQC2", "M7", "SEQC2 high-confidence somatic truth set"),
    "msi/": ("https://github.com/mskcc/msisensor/tree/master/test", "Public example data; cite MSIsensor", "M7", "MSI tumor/normal example BAMs, sites, scores, TCGA baseline"),
    "cnv/": ("https://zenodo.org/records/7515830", "CC BY 4.0", "M7", "COLO829 copy-number segments"),
    "1000g/": ("https://ftp.1000genomes.ebi.ac.uk/vol1/ftp/release/20130502/", "Open (IGSR)", "M6", "1000 Genomes sample panel"),
    "panels_iranome_genes_GRCh38.bed": ("Derived from GENCODE GRCh38.113", "Derived; GENCODE terms", "M3", "Exon BED for the 16 Iranome genes"),
}


def meta_for(rel: str):
    for prefix, value in META.items():
        if rel.startswith(prefix) or rel == prefix:
            return value
    return ("", "", "", "")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def count_vcf(path: Path) -> int | None:
    opener = gzip.open if path.suffix == ".gz" else open
    try:
        with opener(path, "rt", errors="ignore") as handle:
            return sum(1 for line in handle if not line.startswith("#"))
    except (OSError, EOFError, gzip.BadGzipFile):
        return None


def main() -> None:
    rows = []
    for path in sorted(p for p in DATA.rglob("*") if p.is_file()):
        rel = str(path.relative_to(DATA))
        if rel in ("README.md", "manifest.json") or rel.endswith(".log"):
            continue
        source, license_, milestone, note = meta_for(rel)
        row = {
            "path": f"data/{rel}",
            "bytes": path.stat().st_size,
            "sha256": sha256(path),
            "source_url": source,
            "license": license_,
            "milestone": milestone,
            "note": note,
        }
        if path.name.endswith((".vcf", ".vcf.gz")):
            row["vcf_records"] = count_vcf(path)
        rows.append(row)
        print(f"{row['bytes']:>12}  {row['sha256'][:12]}  {rel}")

    manifest = {
        "generated": "2026-11-07",
        "note": "Research-use starter data; see docs/planning/research-workbenches/DATA_SOURCES.md",
        "files": rows,
    }
    (DATA / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"\nwrote {DATA / 'manifest.json'} ({len(rows)} files)")


if __name__ == "__main__":
    main()
