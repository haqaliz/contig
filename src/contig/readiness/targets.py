"""BED and GTF target readers for the readiness workbench."""

from __future__ import annotations

import gzip
from collections import defaultdict
from pathlib import Path

from contig.readiness.models import Target
from contig.variants.vcf import normalize_chrom


def _open_text(path: str | Path):
    path = Path(path)
    if path.suffix == ".gz":
        return gzip.open(path, "rt", errors="replace")
    return path.open("rt", errors="replace")


def load_bed_targets(path: str | Path) -> list[Target]:
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"target BED not found: {path}")

    targets: list[Target] = []
    with _open_text(path) as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped or stripped.startswith(("#", "track", "browser")):
                continue
            fields = stripped.split("\t")
            if len(fields) < 3:
                fields = stripped.split()
            if len(fields) < 3:
                continue
            try:
                start, end = int(fields[1]), int(fields[2])
            except ValueError:
                continue
            if end <= start:
                continue
            chrom = normalize_chrom(fields[0])
            if len(fields) > 3 and fields[3] not in ("", "."):
                name = fields[3]
                gene = name
            else:
                name = f"{chrom}:{start}-{end}"
                gene = ""
            targets.append(Target(chrom, start, end, name, gene=gene))

    targets.sort(key=lambda target: (target.chrom, target.start, target.end, target.name))
    return targets


def load_gtf_targets(path: str | Path, genes: set[str] | list[str]) -> list[Target]:
    gene_set = {gene.upper() for gene in genes}
    if not gene_set:
        raise ValueError("--gtf requires at least one gene in --genes")

    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"GTF not found: {path}")

    rows: dict[str, list[tuple[str, int, int, str, str, str, bool]]] = defaultdict(list)
    with _open_text(path) as handle:
        for line in handle:
            if line.startswith("#"):
                continue
            fields = line.rstrip("\n").split("\t")
            if len(fields) < 9 or fields[2] != "exon":
                continue
            attrs: dict[str, str] = {}
            for item in fields[8].split(";"):
                item = item.strip()
                if " " in item:
                    key, value = item.split(" ", 1)
                    attrs[key] = value.strip('"')
            gene = attrs.get("gene_name", "")
            if gene.upper() not in gene_set:
                continue
            if attrs.get("transcript_type") not in (None, "protein_coding"):
                continue
            rows[gene].append((
                normalize_chrom(fields[0]),
                int(fields[3]) - 1,
                int(fields[4]),
                attrs.get("transcript_id", ""),
                attrs.get("exon_number", ""),
                gene,
                "MANE_Select" in fields[8],
            ))

    targets: list[Target] = []
    for gene, gene_rows in rows.items():
        mane = [row for row in gene_rows if row[6]]
        keep = mane if mane else gene_rows
        for chrom, start, end, transcript, exon, _gene, _mane in keep:
            targets.append(Target(
                chrom=chrom,
                start=start,
                end=end,
                name=f"{gene}:{transcript}:exon{exon}",
                gene=gene,
                transcript=transcript,
                exon=exon,
            ))

    targets.sort(key=lambda target: (target.chrom, target.start, target.end, target.name))
    return targets
