"""Read `samtools depth -a` output into a sparse position->depth map."""

from __future__ import annotations

import gzip
import subprocess
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


def run_samtools_depth(
    bam_path: str | Path,
    bed_path: str | Path,
    output_path: str | Path,
    *,
    reference: str | Path | None = None,
    samtools_bin: str = "samtools",
    timeout: int = 3600,
) -> Path:
    """Run `samtools depth -a -b` and write its TSV to `output_path`."""
    bam_path = Path(bam_path)
    bed_path = Path(bed_path)
    if not bam_path.is_file():
        raise FileNotFoundError(f"alignment not found: {bam_path}")
    if not bed_path.is_file():
        raise FileNotFoundError(f"target BED not found: {bed_path}")
    if reference is not None and not Path(reference).is_file():
        raise FileNotFoundError(f"reference not found: {reference}")

    command = [samtools_bin, "depth", "-a", "-b", str(bed_path)]
    if reference is not None:
        command.extend(["-T", str(reference)])
    command.append(str(bam_path))
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError as exc:
        raise ValueError(f"samtools binary not found: {samtools_bin}") from exc
    except subprocess.TimeoutExpired as exc:
        raise ValueError(f"samtools depth timed out after {timeout}s") from exc
    if result.returncode != 0:
        message = (result.stderr or result.stdout or "").strip()
        raise ValueError(f"samtools depth failed (exit {result.returncode}): {message[:300]}")
    output_path = Path(output_path)
    output_path.write_text(result.stdout, encoding="utf-8")
    return output_path
