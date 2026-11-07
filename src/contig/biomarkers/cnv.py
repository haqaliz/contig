"""Compare copy-number segments against a truth set.

LOH needs allele-specific data and is not verified here; this is a CNV-only
segment-concordance check.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from contig.variants.vcf import normalize_chrom

CHROM_KEYS = ("chrom", "chr", "chromosome", "#chrom")
START_KEYS = ("start", "loc.start", "loc_start", "start_position")
END_KEYS = ("end", "loc.end", "loc_end", "end_position")
VALUE_KEYS = (
    "log2", "log2.copyratio", "log2_copy_ratio", "log2ratio",
    "seg.mean", "copy_number", "copynumber", "cn", "total_cn",
)


@dataclass(frozen=True)
class Segment:
    chrom: str
    start: int
    end: int
    value: float


@dataclass
class CnvResult:
    truth_bases: int
    compared_bases: int
    concordant_bases: int
    concordance: float
    mean_abs_delta: float
    status: str
    tolerance: float
    value_column: str
    detail: str = ""
    call_path: str = ""
    truth_path: str = ""


def _pick(row: dict[str, str], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        if key in row:
            return row[key]
    return None


def load_segments(
    path: str | Path,
    *,
    value_column: str | None = None,
) -> tuple[list[Segment], str]:
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"CNV segments not found: {path}")

    segments: list[Segment] = []
    with path.open("rt", newline="", encoding="utf-8", errors="replace") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if not reader.fieldnames:
            raise ValueError(f"CNV segments need a header: {path}")
        fields = {name.lower(): name for name in reader.fieldnames if name}
        chrom_key = next((key for key in CHROM_KEYS if key in fields), None)
        start_key = next((key for key in START_KEYS if key in fields), None)
        end_key = next((key for key in END_KEYS if key in fields), None)
        value_key = value_column.lower() if value_column else next(
            (key for key in VALUE_KEYS if key in fields), None
        )
        if not all((chrom_key, start_key, end_key, value_key)):
            raise ValueError(
                f"CNV segments need chrom/start/end/value columns: {path}"
            )
        for raw in reader:
            row = {key.lower(): value for key, value in raw.items() if key}
            try:
                start = int(float(row[start_key]))
                end = int(float(row[end_key]))
                value = float(row[value_key])
            except (KeyError, TypeError, ValueError):
                continue
            if end <= start:
                continue
            segments.append(Segment(normalize_chrom(row[chrom_key]), start, end, value))

    if not segments:
        raise ValueError(f"no valid CNV segments in {path}")
    return segments, value_key


def _overlap(a_start: int, a_end: int, b_start: int, b_end: int) -> int:
    return max(0, min(a_end, b_end) - max(a_start, b_start))


def compare_segments(
    call: list[Segment],
    truth: list[Segment],
    *,
    tolerance: float = 0.2,
    min_concordance: float = 0.90,
) -> CnvResult:
    if not 0.0 <= tolerance:
        raise ValueError("cnv_tolerance must be non-negative")
    if not 0.0 <= min_concordance <= 1.0:
        raise ValueError("cnv_min_concordance must be between 0 and 1")

    by_chrom: dict[str, list[Segment]] = {}
    for segment in call:
        by_chrom.setdefault(segment.chrom, []).append(segment)

    truth_bases = sum(segment.end - segment.start for segment in truth)
    compared_bases = 0
    concordant_bases = 0
    delta_sum = 0.0
    for true_segment in truth:
        overlaps = []
        for call_segment in by_chrom.get(true_segment.chrom, []):
            bases = _overlap(call_segment.start, call_segment.end, true_segment.start, true_segment.end)
            if bases:
                overlaps.append((bases, call_segment.value))
        if not overlaps:
            continue
        total = sum(bases for bases, _value in overlaps)
        weighted = sum(bases * value for bases, value in overlaps) / total
        delta = abs(weighted - true_segment.value)
        compared_bases += total
        delta_sum += delta * total
        if delta <= tolerance:
            concordant_bases += total

    if compared_bases == 0:
        return CnvResult(
            truth_bases=truth_bases,
            compared_bases=0,
            concordant_bases=0,
            concordance=0.0,
            mean_abs_delta=0.0,
            status="unverified",
            tolerance=tolerance,
            value_column="",
            detail="no overlapping call/truth segments",
        )
    concordance = concordant_bases / compared_bases
    mean_abs_delta = delta_sum / compared_bases
    status = "match" if concordance >= min_concordance else "divergent"
    return CnvResult(
        truth_bases=truth_bases,
        compared_bases=compared_bases,
        concordant_bases=concordant_bases,
        concordance=concordance,
        mean_abs_delta=mean_abs_delta,
        status=status,
        tolerance=tolerance,
        value_column="",
        detail=(
            f"{concordance:.1%} of compared bases within {tolerance:g}; "
            f"mean |delta| {mean_abs_delta:.3f}"
        ),
    )


def compare_files(
    call_path: str | Path,
    truth_path: str | Path,
    *,
    value_column: str | None = None,
    tolerance: float = 0.2,
    min_concordance: float = 0.90,
) -> CnvResult:
    call, call_column = load_segments(call_path, value_column=value_column)
    truth, truth_column = load_segments(truth_path, value_column=value_column or call_column)
    result = compare_segments(call, truth, tolerance=tolerance, min_concordance=min_concordance)
    result.value_column = call_column
    result.call_path = str(call_path)
    result.truth_path = str(truth_path)
    return result
