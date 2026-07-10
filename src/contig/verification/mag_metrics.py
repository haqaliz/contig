"""QUAST + CheckM stats parsers for mag (shotgun metagenomics) metric ingestion.

The mag rule pack (`MAG_RULE_PACK`) scores three per-bin metrics — `n50`,
`completeness`, `contamination` — but the exact MultiQC general-stats slug for
these is unverified (the source pack docstring flags it), so the pack
silently no-ops on a real nf-core/mag run. These parsers read QUAST's and
CheckM's own on-disk stats artifacts directly.

Structural difference from the methylseq/Bismark parsers this mirrors (and
same shape as the ampliseq/DADA2 parsers): QUAST's `transposed_report.tsv`
and CheckM's summary table are each a SINGLE file covering MANY bins (rows
keyed by bin), not one file per bin. Both parsers here therefore return
`{bin: {slug: float}}` directly, and the runner's mag gate merges the two
dicts by bin id.

All parsers are pure: they read only the passed file, no network, no
randomness. A metric that is absent or non-numeric is OMITTED (never
guessed), so the gate degrades to UNVERIFIED rather than fabricating a pass.

Coverage:
- `transposed_report.tsv` (QUAST's per-bin assembly-stats table, header row +
  one row per bin/assembly): the `N50` column -> `n50`. Column names are
  matched case-insensitively.
- CheckM summary (a quality TSV with `Bin Id`, `Completeness`, `Contamination`
  columns, header row + one row per bin): `Completeness` -> `completeness`,
  `Contamination` -> `contamination`. Column names are matched
  case-insensitively.
"""

from __future__ import annotations

import csv
from os import PathLike
from pathlib import Path

# Canonical slug names, matching MAG_RULE_PACK in rule_pack.py.
N50 = "n50"
COMPLETENESS = "completeness"
CONTAMINATION = "contamination"

_BIN_COLUMN_NAMES = {"assembly", "bin", "bin id", "binid", "bin_id"}
_N50_COLUMN_NAMES = {"n50"}
_COMPLETENESS_COLUMN_NAMES = {"completeness"}
_CONTAMINATION_COLUMN_NAMES = {"contamination"}


def _to_float(text: str | None) -> float | None:
    """Parse a plain numeric string; return None on anything non-numeric.

    Callers OMIT a slug when this returns None rather than inventing a value.
    """
    if text is None:
        return None
    try:
        return float(text.strip())
    except (ValueError, AttributeError):
        return None


def _read_tsv_rows(path: str | PathLike[str]) -> list[list[str]]:
    text = Path(path).read_text()
    lines = [line for line in text.splitlines() if line.strip() != ""]
    if not lines:
        return []
    return list(csv.reader(lines, delimiter="\t"))


# --------------------------------------------------------------------------- #
# transposed_report.tsv — header-driven, multi-bin QUAST assembly-stats table.
# --------------------------------------------------------------------------- #


def parse_quast_report(path: str | PathLike[str]) -> dict[str, dict[str, float]]:
    """Parse QUAST's `transposed_report.tsv` into `{bin: {n50: float}}`.

    A file whose header carries no `N50` column at all (i.e. not recognizable
    as a QUAST transposed report) is treated as unrecognized and returns `{}`
    rather than guessing a bin column.
    """
    rows = _read_tsv_rows(path)
    if not rows:
        return {}
    header = [cell.strip().lower() for cell in rows[0]]

    n50_idx = next((i for i, h in enumerate(header) if h in _N50_COLUMN_NAMES), None)
    if n50_idx is None:
        return {}

    bin_idx = next((i for i, h in enumerate(header) if h in _BIN_COLUMN_NAMES), 0)

    out: dict[str, dict[str, float]] = {}
    for row in rows[1:]:
        if bin_idx >= len(row):
            continue
        bin_id = row[bin_idx].strip()
        if not bin_id:
            continue
        metrics: dict[str, float] = {}
        n50_value = _to_float(row[n50_idx]) if n50_idx < len(row) else None
        if n50_value is not None:
            metrics[N50] = n50_value
        out[bin_id] = metrics
    return out


# --------------------------------------------------------------------------- #
# CheckM summary — header-driven, multi-bin bin-quality table.
# --------------------------------------------------------------------------- #


def parse_checkm_summary(path: str | PathLike[str]) -> dict[str, dict[str, float]]:
    """Parse a CheckM summary table into `{bin: {completeness, contamination}}`.

    A file whose header carries neither a `Completeness` nor a `Contamination`
    column (i.e. not recognizable as a CheckM summary at all) is treated as
    unrecognized and returns `{}` rather than guessing a bin column.
    """
    rows = _read_tsv_rows(path)
    if not rows:
        return {}
    header = [cell.strip().lower() for cell in rows[0]]

    completeness_idx = next(
        (i for i, h in enumerate(header) if h in _COMPLETENESS_COLUMN_NAMES), None
    )
    contamination_idx = next(
        (i for i, h in enumerate(header) if h in _CONTAMINATION_COLUMN_NAMES), None
    )
    if completeness_idx is None and contamination_idx is None:
        return {}

    bin_idx = next((i for i, h in enumerate(header) if h in _BIN_COLUMN_NAMES), 0)

    out: dict[str, dict[str, float]] = {}
    for row in rows[1:]:
        if bin_idx >= len(row):
            continue
        bin_id = row[bin_idx].strip()
        if not bin_id:
            continue
        metrics: dict[str, float] = {}
        completeness_value = (
            _to_float(row[completeness_idx])
            if completeness_idx is not None and completeness_idx < len(row)
            else None
        )
        contamination_value = (
            _to_float(row[contamination_idx])
            if contamination_idx is not None and contamination_idx < len(row)
            else None
        )
        if completeness_value is not None:
            metrics[COMPLETENESS] = completeness_value
        if contamination_value is not None:
            metrics[CONTAMINATION] = contamination_value
        out[bin_id] = metrics
    return out
