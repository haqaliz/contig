"""Homology/pseudogene caveat BED reader and overlap."""

from __future__ import annotations

import gzip
from pathlib import Path

from contig.readiness.models import CaveatRegion, Target
from contig.variants.vcf import normalize_chrom


def _open_text(path: str | Path):
    path = Path(path)
    if path.suffix == ".gz":
        return gzip.open(path, "rt", errors="replace")
    return path.open("rt", errors="replace")


def load_caveats(path: str | Path) -> list[CaveatRegion]:
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"caveat BED not found: {path}")

    regions: list[CaveatRegion] = []
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
            if len(fields) >= 8:
                name = f"{fields[3]}/{fields[6]}"
                reason = fields[7]
            elif len(fields) >= 5:
                name = fields[3]
                reason = fields[4]
            elif len(fields) >= 4:
                name = fields[3]
                reason = fields[3]
            else:
                name = f"{fields[0]}:{start}-{end}"
                reason = "caveat region"
            regions.append(CaveatRegion(normalize_chrom(fields[0]), start, end, name, reason))

    regions.sort(key=lambda region: (region.chrom, region.start, region.end, region.name))
    return regions


def overlapping_caveats(target: Target, caveats: list[CaveatRegion]) -> list[CaveatRegion]:
    chrom = normalize_chrom(target.chrom)
    return [
        caveat for caveat in caveats
        if caveat.chrom == chrom
        and target.start < caveat.end
        and caveat.start < target.end
    ]
