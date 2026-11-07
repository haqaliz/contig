"""Compute TMB from a somatic VCF and a callable-region BED."""

from __future__ import annotations

from bisect import bisect_right
from pathlib import Path

from contig.variants.vcf import normalize_chrom, read_variants

CODING_CONSEQUENCES = {
    "transcript_ablation",
    "splice_acceptor_variant",
    "splice_donor_variant",
    "stop_gained",
    "frameshift_variant",
    "stop_lost",
    "start_lost",
    "transcript_amplification",
    "inframe_insertion",
    "inframe_deletion",
    "missense_variant",
    "protein_altering_variant",
    "splice_region_variant",
    "incomplete_terminal_codon_variant",
    "start_retained_variant",
    "stop_retained_variant",
    "synonymous_variant",
    "coding_sequence_variant",
}


def _open_text(path: str | Path):
    path = Path(path)
    if path.suffix == ".gz":
        import gzip
        return gzip.open(path, "rt", errors="replace")
    return path.open("rt", errors="replace")


def load_callable_bed(
    path: str | Path,
) -> tuple[dict[str, list[tuple[int, int]]], dict[str, list[int]], float]:
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"callable BED not found: {path}")

    intervals: dict[str, list[tuple[int, int]]] = {}
    total_bases = 0
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
            intervals.setdefault(chrom, []).append((start, end))
            total_bases += end - start

    for chrom in intervals:
        intervals[chrom].sort()
    if total_bases <= 0:
        raise ValueError(f"callable BED has no intervals: {path}")
    starts = {chrom: [start for start, _ in regions] for chrom, regions in intervals.items()}
    return intervals, starts, total_bases / 1_000_000


def in_callable(
    intervals: dict[str, list[tuple[int, int]]],
    starts: dict[str, list[int]],
    chrom: str,
    pos: int,
) -> bool:
    chrom = normalize_chrom(chrom)
    regions = intervals.get(chrom)
    if not regions:
        return False
    index = bisect_right(starts[chrom], pos) - 1
    if index < 0:
        return False
    start, end = regions[index]
    return start < pos <= end


def _is_pass(value: str) -> bool:
    if value in {"PASS", "."}:
        return True
    return "PASS" in value.split(";")


def compute_tmb(
    vcf_path: str | Path,
    bed_path: str | Path,
    *,
    coding_only: bool = False,
) -> dict[str, object]:
    vcf_path = Path(vcf_path)
    if not vcf_path.is_file():
        raise FileNotFoundError(f"VCF not found: {vcf_path}")
    rows, stats = read_variants(vcf_path)
    intervals, starts, callable_mb = load_callable_bed(bed_path)

    counted = 0
    outside = 0
    unannotated = 0
    for row in rows:
        if not _is_pass(row.filter):
            continue
        if not in_callable(intervals, starts, row.key.chrom, row.key.pos):
            outside += 1
            continue
        if coding_only:
            if not row.consequence or row.consequence not in CODING_CONSEQUENCES:
                unannotated += 1
                continue
        counted += 1

    definition = "PASS variants in callable regions"
    if coding_only:
        definition += " with a coding consequence (unannotated variants excluded)"
    return {
        "variant_count": counted,
        "callable_mb": callable_mb,
        "tmb": counted / callable_mb if callable_mb else 0.0,
        "outside_count": outside,
        "unannotated_count": unannotated,
        "definition": definition,
        "records": stats.total_records,
        "skipped": stats.skipped_lines,
    }
