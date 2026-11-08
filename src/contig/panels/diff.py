"""Compare two panel versions (metadata and BED intervals)."""

from __future__ import annotations

from contig.panels.build import _chrom_sort
from contig.panels.models import Panel

_META_FIELDS = (
    "name",
    "build",
    "version",
    "source",
    "genes",
    "transcripts",
    "method",
    "checksum",
    "sources",
)


def _intervals(bed_text: str) -> list[tuple[str, ...]]:
    rows = []
    for line in bed_text.splitlines():
        fields = tuple(line.split("\t"))
        if len(fields) >= 3:
            rows.append(fields)
    return rows


def _row_key(row: tuple[str, ...]) -> tuple:
    try:
        start, end = int(row[1]), int(row[2])
    except (IndexError, ValueError):
        start, end = 0, 0
    return (_chrom_sort(row[0]), start, end, row[3:])


def panel_diff(a: Panel, b: Panel) -> dict:
    """Metadata and interval differences between panels ``a`` and ``b``.

    ``a`` is the baseline (removed intervals), ``b`` the comparison (added
    intervals). Created timestamps are deliberately ignored: rebuilding the same
    content is not a content difference.
    """
    changes: dict[str, dict[str, object]] = {}
    for field in _META_FIELDS:
        left = getattr(a.meta, field)
        right = getattr(b.meta, field)
        if field == "sources":
            left = [source.model_dump() for source in left]
            right = [source.model_dump() for source in right]
        if left != right:
            changes[field] = {"a": left, "b": right}
    left_rows = set(_intervals(a.bed_text))
    right_rows = set(_intervals(b.bed_text))
    added = sorted(right_rows - left_rows, key=_row_key)
    removed = sorted(left_rows - right_rows, key=_row_key)
    return {
        "same": not changes and not added and not removed,
        "meta": changes,
        "added": added,
        "removed": removed,
    }


def render_panel_diff(result: dict) -> str:
    if result["same"]:
        return "Panels are identical.\n"
    lines = [f"Metadata changes: {len(result['meta'])}"]
    for field, change in sorted(result["meta"].items()):
        lines.append(f"  {field}: {change['a']!r} -> {change['b']!r}")
    lines.append(f"Intervals added: {len(result['added'])}")
    for row in result["added"]:
        lines.append("  + " + "\t".join(row))
    lines.append(f"Intervals removed: {len(result['removed'])}")
    for row in result["removed"]:
        lines.append("  - " + "\t".join(row))
    return "\n".join(lines) + "\n"
