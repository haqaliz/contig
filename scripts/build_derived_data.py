#!/usr/bin/env python3
"""Build small derived BEDs from the downloaded GENCODE/Ensembl GTF.

Outputs:
  data/panels_iranome_genes_GRCh38.bed     exon BED for the 16 Iranome genes
  data/homology/homology_caveats_GRCh38.bed  SMN1/SMN2, PMS2/PMS2CL, HBA1/HBA2

Both are research-use fixtures. Rebuild after changing the GTF.
"""

from __future__ import annotations

import gzip
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GTF = ROOT / "data/ensembl/Homo_sapiens.GRCh38.113.gtf.gz"

PANEL_GENES = {
    "BRCA1", "BRCA2", "PALB2", "TP53", "PTEN", "ATM", "CHEK2",
    "CFTR", "GJB2", "SMN1", "MLH1", "MSH2", "MSH6", "PMS2",
    "EGFR", "MYBPC3",
}
HOMOLOGY_PAIRS = {
    "SMN1": "SMN2", "SMN2": "SMN1",
    "PMS2": "PMS2CL", "PMS2CL": "PMS2",
    "HBA1": "HBA2", "HBA2": "HBA1",
}
REASONS = {
    "SMN1": "homology with SMN2; CNV needed for exon 7-8",
    "SMN2": "homology with SMN1",
    "PMS2": "pseudogene PMS2CL; check MAPQ",
    "PMS2CL": "pseudogene of PMS2",
    "HBA1": "homology with HBA2",
    "HBA2": "homology with HBA1",
}


def parse() -> dict[str, list[tuple]]:
    genes = PANEL_GENES | set(HOMOLOGY_PAIRS)
    by_gene: dict[str, list[tuple]] = defaultdict(list)
    with gzip.open(GTF, "rt") as handle:
        for line in handle:
            if line.startswith("#"):
                continue
            fields = line.rstrip("\n").split("\t")
            if len(fields) < 9 or fields[2] != "exon":
                continue
            attrs = {}
            for item in fields[8].split(";"):
                item = item.strip()
                if " " in item:
                    key, value = item.split(" ", 1)
                    attrs[key] = value.strip('"')
            gene = attrs.get("gene_name")
            if gene not in genes:
                continue
            if attrs.get("transcript_type") not in (None, "protein_coding"):
                continue
            mane = "MANE_Select" in fields[8]
            by_gene[gene].append((
                fields[0], int(fields[3]) - 1, int(fields[4]), gene,
                attrs.get("transcript_id", ""), attrs.get("exon_number", ""), mane,
            ))
    return by_gene


def main() -> None:
    by_gene = parse()

    panel_rows = []
    for gene, rows in by_gene.items():
        if gene not in PANEL_GENES:
            continue
        mane = [row for row in rows if row[6]]
        panel_rows.extend(mane if mane else rows)
    panel_rows.sort(key=lambda row: (row[0], row[1], row[2]))
    panel = ROOT / "data/panels_iranome_genes_GRCh38.bed"
    panel.parent.mkdir(parents=True, exist_ok=True)
    with panel.open("w") as handle:
        for row in panel_rows:
            handle.write("\t".join(map(str, row[:6])) + "\n")

    homology_rows = []
    for gene, rows in by_gene.items():
        if gene not in HOMOLOGY_PAIRS:
            continue
        for row in rows:
            homology_rows.append((
                row[0], row[1], row[2], gene, row[4], row[5],
                HOMOLOGY_PAIRS[gene], REASONS[gene],
            ))
    homology_rows.sort(key=lambda row: (row[0], row[1], row[2]))
    homology = ROOT / "data/homology/homology_caveats_GRCh38.bed"
    homology.parent.mkdir(parents=True, exist_ok=True)
    with homology.open("w") as handle:
        handle.write("#chrom\tstart\tend\tgene\ttranscript\texon\tpartner\treason\n")
        for row in homology_rows:
            handle.write("\t".join(map(str, row)) + "\n")

    print(f"panel: {len(panel_rows)} exons -> {panel}")
    print(f"homology: {len(homology_rows)} exons -> {homology}")


if __name__ == "__main__":
    main()
