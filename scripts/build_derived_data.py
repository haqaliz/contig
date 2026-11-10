#!/usr/bin/env python3
"""Build small derived BEDs from the downloaded GENCODE/Ensembl GTF.

Outputs:
  data/panels_iranome_genes_GRCh38.bed     exon BED for the 16 Iranome genes
  data/homology/homology_caveats_GRCh38.bed  curated homology/pseudogene exons

The homology BED uses one representative transcript per gene (MANE Select,
else Ensembl canonical) and one row per exon/partner. Both are research-use
fixtures. Rebuild after changing the GTF.
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
    "SMN1": ("SMN2",),
    "SMN2": ("SMN1",),
    "PMS2": ("PMS2CL",),
    "PMS2CL": ("PMS2",),
    "HBA1": ("HBA2",),
    "HBA2": ("HBA1",),
    "CYP21A2": ("CYP21A1P",),
    "CYP21A1P": ("CYP21A2",),
    "GBA1": ("GBA1LP",),
    "GBA1LP": ("GBA1",),
    "PKD1": ("PKD1P1", "PKD1P2", "PKD1P3", "PKD1P4", "PKD1P5", "PKD1P6"),
    "PKD1P1": ("PKD1",),
    "PKD1P2": ("PKD1",),
    "PKD1P3": ("PKD1",),
    "PKD1P4": ("PKD1",),
    "PKD1P5": ("PKD1",),
    "PKD1P6": ("PKD1",),
    "STRC": ("STRCP1",),
    "STRCP1": ("STRC",),
    "NCF1": ("NCF1B", "NCF1C"),
    "NCF1B": ("NCF1",),
    "NCF1C": ("NCF1",),
    "CYP2D6": ("CYP2D7", "CYP2D8P"),
    "CYP2D7": ("CYP2D6",),
    "CYP2D8P": ("CYP2D6",),
    "PTEN": ("PTENP1",),
    "PTENP1": ("PTEN",),
    "GJB2": ("GJB6",),
    "GJB6": ("GJB2",),
    "IKBKG": ("IKBKGP1",),
    "IKBKGP1": ("IKBKG",),
    "HBB": ("HBD",),
    "HBD": ("HBB",),
}
REASONS = {
    "SMN1": "homology with SMN2; CNV needed for exon 7-8",
    "SMN2": "homology with SMN1",
    "PMS2": "pseudogene PMS2CL; check MAPQ",
    "PMS2CL": "pseudogene of PMS2",
    "HBA1": "homology with HBA2",
    "HBA2": "homology with HBA1",
    "CYP21A2": "pseudogene CYP21A1P; high homology, check MAPQ/CNV",
    "CYP21A1P": "pseudogene of CYP21A2",
    "GBA1": "pseudogene GBA1LP (GBAP1); high homology, check MAPQ",
    "GBA1LP": "pseudogene of GBA1 (also called GBAP1)",
    "PKD1": "homology with PKD1P1-P6 pseudogenes; check MAPQ",
    "PKD1P1": "pseudogene of PKD1",
    "PKD1P2": "pseudogene of PKD1",
    "PKD1P3": "pseudogene of PKD1",
    "PKD1P4": "pseudogene of PKD1",
    "PKD1P5": "pseudogene of PKD1",
    "PKD1P6": "pseudogene of PKD1",
    "STRC": "pseudogene STRCP1; high homology, check MAPQ",
    "STRCP1": "pseudogene of STRC",
    "NCF1": "homology with NCF1B/NCF1C pseudogenes; CNV/MAPQ",
    "NCF1B": "pseudogene of NCF1",
    "NCF1C": "pseudogene of NCF1",
    "CYP2D6": "pseudogenes CYP2D7/CYP2D8P; check MAPQ/CNV",
    "CYP2D7": "pseudogene of CYP2D6",
    "CYP2D8P": "pseudogene of CYP2D6",
    "PTEN": "processed pseudogene PTENP1; check MAPQ",
    "PTENP1": "processed pseudogene of PTEN",
    "GJB2": "homologous GJB6; GJB6 deletion/duplication affects interpretation",
    "GJB6": "homologous GJB2; deletion/duplication affects GJB2",
    "IKBKG": "pseudogene IKBKGP1; high homology, check MAPQ",
    "IKBKGP1": "pseudogene of IKBKG",
    "HBB": "homologous HBD; check MAPQ",
    "HBD": "homologous HBB; check MAPQ",
}


def parse() -> dict[str, list[tuple]]:
    genes = PANEL_GENES | set(HOMOLOGY_PAIRS)
    genes |= {partner for partners in HOMOLOGY_PAIRS.values() for partner in partners}
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
            biotype = attrs.get("transcript_biotype") or attrs.get("transcript_type")
            if (
                biotype is not None
                and not biotype.startswith("protein_coding")
                and not biotype.endswith("pseudogene")
            ):
                continue
            mane = "MANE_Select" in fields[8]
            canonical = "Ensembl_canonical" in fields[8]
            by_gene[gene].append((
                fields[0], int(fields[3]) - 1, int(fields[4]), gene,
                attrs.get("transcript_id", ""), attrs.get("exon_number", ""),
                mane, canonical,
            ))
    return by_gene


def _validate_config() -> None:
    for gene, partners in HOMOLOGY_PAIRS.items():
        if gene not in REASONS:
            raise SystemExit(f"homology gene missing a reason: {gene}")
        for partner in partners:
            if partner not in HOMOLOGY_PAIRS:
                raise SystemExit(f"homology partner missing from the map: {partner}")
            if gene not in HOMOLOGY_PAIRS[partner]:
                raise SystemExit(
                    f"homology pair is not symmetric: {gene} -> {partner}"
                )


def _representative_rows(rows: list[tuple]) -> list[tuple]:
    """One transcript per gene: MANE Select, else Ensembl canonical, else most exons."""
    representative = [row for row in rows if row[6]] or [
        row for row in rows if row[7]
    ]
    if representative:
        transcript = representative[0][4]
        return [row for row in representative if row[4] == transcript]
    counts: dict[str, int] = defaultdict(int)
    for row in rows:
        counts[row[4]] += 1
    transcript = max(counts, key=lambda item: (counts[item], item))
    return [row for row in rows if row[4] == transcript]


def main() -> None:
    _validate_config()
    by_gene = parse()
    missing = sorted(set(HOMOLOGY_PAIRS) - set(by_gene))
    if missing:
        raise SystemExit(f"homology genes missing from the GTF: {', '.join(missing)}")

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
        representative = _representative_rows(rows)
        seen: set[tuple[str, int, int]] = set()
        for row in representative:
            key = (row[0], row[1], row[2])
            if key in seen:
                continue
            seen.add(key)
            for partner in HOMOLOGY_PAIRS[gene]:
                homology_rows.append((
                    row[0], row[1], row[2], gene, row[4], row[5],
                    partner, REASONS[gene],
                ))
    homology_rows.sort(key=lambda row: (row[0], row[1], row[2], row[3], row[6]))
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
