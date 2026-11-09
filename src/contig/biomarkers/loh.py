"""LOH verification from allele-specific copy-number segments.

A segment is LOH when its minor copy number is 0 (ASCAT/FACETS/GDC
`Minor_Copy_Number`). The comparator uses base-level Jaccard overlap between
the call's LOH intervals and the truth's LOH intervals. It never guesses from
total copy number alone: a file without a minor-copy-number column is refused.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from contig.variants.vcf import normalize_chrom

CHROM_KEYS = ("chromosome", "chrom", "chr", "#chrom")
START_KEYS = ("start", "loc.start", "loc_start", "start_position")
END_KEYS = ("end", "loc.end", "loc_end", "end_position")
MINOR_KEYS = (
    "minor_copy_number",
    "minor_cn",
    "minorcn",
    "nminor",
    "lcn.em",
    "minor",
)
LOH_MINOR_CN = 0.5


@dataclass(frozen=True)
class LohSegment:
    chrom: str
    start: int
    end: int
    minor_cn: float


@dataclass
class LohResult:
    truth_loh_bases: int
    call_loh_bases: int
    overlap_bases: int
    precision: float
    recall: float
    jaccard: float
    status: str
    min_agreement: float
    minor_column: str
    detail: str = ""
    call_path: str = ""
    truth_path: str = ""


def _pick(fields: dict[str, str], keys: tuple[str, ...]) -> str | None:
    return next((fields[key] for key in keys if key in fields), None)


def load_allele_specific_segments(path: str | Path) -> tuple[list[LohSegment], str]:
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"allele-specific segments not found: {path}")
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    if not lines:
        raise ValueError(f"empty allele-specific segment file: {path}")
    delimiter = "\t" if "\t" in lines[0] else None
    header = lines[0].split(delimiter) if delimiter else lines[0].split()
    fields = {name.strip().lower(): name for name in header if name.strip()}
    chrom_key = next((key for key in CHROM_KEYS if key in fields), None)
    start_key = next((key for key in START_KEYS if key in fields), None)
    end_key = next((key for key in END_KEYS if key in fields), None)
    minor_key = next((key for key in MINOR_KEYS if key in fields), None)
    if not all((chrom_key, start_key, end_key, minor_key)):
        raise ValueError(
            "allele-specific segments need chrom/start/end/minor-copy-number "
            f"columns (for example Minor_Copy_Number): {path}"
        )

    segments: list[LohSegment] = []
    for line in lines[1:]:
        if not line.strip() or line.startswith("#"):
            continue
        values = line.split(delimiter) if delimiter else line.split()
        if len(values) < len(header):
            continue
        row = {name.strip().lower(): value for name, value in zip(header, values)}
        try:
            start = int(float(row[start_key]))
            end = int(float(row[end_key]))
            minor = float(row[minor_key])
        except (KeyError, TypeError, ValueError):
            continue
        if end <= start:
            continue
        segments.append(
            LohSegment(normalize_chrom(row[chrom_key]), start, end, minor)
        )
    if not segments:
        raise ValueError(f"no valid allele-specific segments in {path}")
    return segments, minor_key


def _merge(segments: list[LohSegment]) -> list[LohSegment]:
    by_chrom: dict[str, list[LohSegment]] = {}
    for segment in segments:
        by_chrom.setdefault(segment.chrom, []).append(segment)
    merged: list[LohSegment] = []
    for chrom, chrom_segments in by_chrom.items():
        chrom_segments.sort(key=lambda segment: (segment.start, segment.end))
        current_start = current_end = None
        for segment in chrom_segments:
            if current_start is None:
                current_start, current_end = segment.start, segment.end
            elif segment.start <= current_end:
                current_end = max(current_end, segment.end)
            else:
                merged.append(LohSegment(chrom, current_start, current_end, 0.0))
                current_start, current_end = segment.start, segment.end
        if current_start is not None:
            merged.append(LohSegment(chrom, current_start, current_end, 0.0))
    return merged


def _bases(segments: list[LohSegment]) -> int:
    return sum(segment.end - segment.start for segment in segments)


def _overlap(call: list[LohSegment], truth: list[LohSegment]) -> int:
    by_chrom: dict[str, list[LohSegment]] = {}
    for segment in call:
        by_chrom.setdefault(segment.chrom, []).append(segment)
    total = 0
    for true_segment in truth:
        for call_segment in by_chrom.get(true_segment.chrom, []):
            total += max(
                0,
                min(call_segment.end, true_segment.end)
                - max(call_segment.start, true_segment.start),
            )
    return total


def compare_loh(
    call: list[LohSegment],
    truth: list[LohSegment],
    *,
    min_agreement: float = 0.90,
) -> LohResult:
    if not 0.0 <= min_agreement <= 1.0:
        raise ValueError("loh_min_agreement must be between 0 and 1")
    call_loh = _merge([s for s in call if s.minor_cn < LOH_MINOR_CN])
    truth_loh = _merge([s for s in truth if s.minor_cn < LOH_MINOR_CN])
    truth_bases = _bases(truth_loh)
    call_bases = _bases(call_loh)
    overlap = _overlap(call_loh, truth_loh)

    if not truth_loh:
        return LohResult(
            truth_loh_bases=0,
            call_loh_bases=call_bases,
            overlap_bases=0,
            precision=0.0,
            recall=0.0,
            jaccard=0.0,
            status="unverified",
            min_agreement=min_agreement,
            minor_column="",
            detail="truth has no LOH segments",
        )
    if not call_loh:
        return LohResult(
            truth_loh_bases=truth_bases,
            call_loh_bases=0,
            overlap_bases=0,
            precision=0.0,
            recall=0.0,
            jaccard=0.0,
            status="divergent",
            min_agreement=min_agreement,
            minor_column="",
            detail=f"call has no LOH segments; truth has {truth_bases} LOH bases",
        )
    shared_chroms = {s.chrom for s in call} & {s.chrom for s in truth}
    if not shared_chroms:
        return LohResult(
            truth_loh_bases=truth_bases,
            call_loh_bases=call_bases,
            overlap_bases=0,
            precision=0.0,
            recall=0.0,
            jaccard=0.0,
            status="unverified",
            min_agreement=min_agreement,
            minor_column="",
            detail="no shared chromosomes between call and truth",
        )

    precision = overlap / call_bases if call_bases else 0.0
    recall = overlap / truth_bases if truth_bases else 0.0
    union = call_bases + truth_bases - overlap
    jaccard = overlap / union if union else 0.0
    status = "match" if jaccard >= min_agreement else "divergent"
    return LohResult(
        truth_loh_bases=truth_bases,
        call_loh_bases=call_bases,
        overlap_bases=overlap,
        precision=precision,
        recall=recall,
        jaccard=jaccard,
        status=status,
        min_agreement=min_agreement,
        minor_column="",
        detail=(
            f"{jaccard:.1%} LOH Jaccard; precision {precision:.1%}, recall "
            f"{recall:.1%}; {truth_bases} truth / {call_bases} call LOH bases"
        ),
    )


def compare_loh_files(
    call_path: str | Path,
    truth_path: str | Path,
    *,
    min_agreement: float = 0.90,
) -> LohResult:
    call, call_column = load_allele_specific_segments(call_path)
    truth, _truth_column = load_allele_specific_segments(truth_path)
    result = compare_loh(call, truth, min_agreement=min_agreement)
    result.minor_column = call_column
    result.call_path = str(call_path)
    result.truth_path = str(truth_path)
    return result
