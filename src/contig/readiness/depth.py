"""Read `samtools depth -a` output into a sparse position->depth map."""

from __future__ import annotations

import gzip
from dataclasses import dataclass
from pathlib import Path

from contig.variants.vcf import normalize_chrom


@dataclass
class DepthStats:
    lines: int = 0
    positions: int = 0
    skipped: int = 0
    duplicates: int = 0


def _open_text(path: str | Path):
    path = Path(path)
    if path.suffix == ".gz":
        return gzip.open(path, "rt", errors="replace")
    return path.open("rt", errors="replace")


def load_depth(path: str | Path) -> tuple[dict[tuple[str, int], int], DepthStats]:
    """Parse `chrom pos depth` lines. Missing positions stay absent (read as 0)."""

    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"depth file not found: {path}")

    depths: dict[tuple[str, int], int] = {}
    stats = DepthStats()
    with _open_text(path) as handle:
        for line in handle:
            if not line.strip() or line.startswith("#"):
                continue
            fields = line.split()
            if len(fields) < 3:
                stats.skipped += 1
                continue
            if fields[0].lower() == "chrom":
                continue
            try:
                key = (normalize_chrom(fields[0]), int(fields[1]))
                value = int(float(fields[2]))
            except ValueError:
                stats.skipped += 1
                continue
            if value < 0:
                stats.skipped += 1
                continue
            stats.lines += 1
            if key in depths:
                stats.duplicates += 1
            depths[key] = value

    stats.positions = len(depths)
    return depths, stats
