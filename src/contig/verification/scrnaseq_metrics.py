"""Single-cell (scrnaseq) cell-QC parsers.

The scrnaseq rule pack (`SCRNASEQ_RULE_PACK`) scores three per-sample metrics —
`estimated_cells`, `median_genes_per_cell`, `fraction_reads_in_cells` — but the
base nf-core/scrnaseq pipeline does NOT route them into MultiQC general-stats, so
the pack silently no-ops. These parsers read the cell-QC the aligner writes to
disk and return `{slug: float}` for ONE sample, which the runner's scrnaseq gate
feeds to `evaluate()`.

All parsers are pure: they read only the passed file, no network, no randomness.
A metric that is absent or non-numeric is OMITTED (never guessed to 0), so the
gate degrades to UNVERIFIED rather than fabricating a pass.

Coverage by aligner path:
- STARsolo (`--aligner star`): `Summary.csv` — `parse_starsolo_summary`.
- Cell Ranger (`--aligner cellranger`): `metrics_summary.csv` — `parse_cellranger_metrics`.
- simpleaf/alevin-fry (the pinned 4.1.0 DEFAULT): no confirmed machine-readable
  cell-QC artifact (it emits AlevinQC/QCatch HTML), so `parse_simpleaf_metrics`
  returns `{}` (→ UNVERIFIED). We do NOT scrape HTML.
"""

from __future__ import annotations

import csv
from os import PathLike
from pathlib import Path

# Canonical slug names, matching SCRNASEQ_RULE_PACK in rule_pack.py.
ESTIMATED_CELLS = "estimated_cells"
MEDIAN_GENES_PER_CELL = "median_genes_per_cell"
FRACTION_READS_IN_CELLS = "fraction_reads_in_cells"


def _to_float(text: str) -> float | None:
    """Parse a plain numeric string; return None on anything non-numeric.

    Callers OMIT a slug when this returns None rather than inventing a value.
    """
    try:
        return float(text.strip())
    except (ValueError, AttributeError):
        return None


# --------------------------------------------------------------------------- #
# STARsolo Summary.csv
# --------------------------------------------------------------------------- #

# STARsolo writes a headerless `Field,Value` CSV (Solo.out/Gene/Summary.csv).
# Field labels are matched case-insensitively; both "Gene" and "Genes" spellings
# of the median field are accepted (they vary by STAR version).
_STARSOLO_FIELD_MAP: dict[str, str] = {
    "estimated number of cells": ESTIMATED_CELLS,
    "median gene per cell": MEDIAN_GENES_PER_CELL,
    "median genes per cell": MEDIAN_GENES_PER_CELL,
    "fraction of unique reads in cells": FRACTION_READS_IN_CELLS,
}


def parse_starsolo_summary(path: str | PathLike[str]) -> dict[str, float]:
    """Parse a STARsolo `Summary.csv` into `{slug: float}` for one sample.

    `fraction_reads_in_cells` is already a 0-1 fraction in STARsolo output.
    Unmapped rows are ignored; a non-numeric value omits its slug.
    """
    out: dict[str, float] = {}
    with open(path, newline="") as fh:
        for row in csv.reader(fh):
            if len(row) < 2:
                continue
            slug = _STARSOLO_FIELD_MAP.get(row[0].strip().lower())
            if slug is None:
                continue
            value = _to_float(row[1])
            if value is not None:
                out[slug] = value
    return out


# --------------------------------------------------------------------------- #
# Cell Ranger metrics_summary.csv
# --------------------------------------------------------------------------- #

# Cell Ranger writes a two-line CSV: a quoted header row + a quoted value row.
# Values carry comma-thousands ("5,000") and, for rate columns, a percent suffix
# ("92.3%"). `is_percent` marks a column whose value must be divided by 100 so its
# unit matches the pack band (fraction_reads_in_cells warn_below 0.7, a fraction).
_CELLRANGER_FIELD_MAP: dict[str, tuple[str, bool]] = {
    "estimated number of cells": (ESTIMATED_CELLS, False),
    "median genes per cell": (MEDIAN_GENES_PER_CELL, False),
    "fraction reads in cells": (FRACTION_READS_IN_CELLS, True),
}


def _parse_cellranger_number(text: str, is_percent: bool) -> float | None:
    """Strip comma-thousands and a trailing percent, dividing percents by 100."""
    cleaned = text.strip().replace(",", "")
    if is_percent:
        cleaned = cleaned.rstrip("%").strip()
        value = _to_float(cleaned)
        return None if value is None else value / 100.0
    return _to_float(cleaned)


def parse_cellranger_metrics(path: str | PathLike[str]) -> dict[str, float]:
    """Parse a Cell Ranger `metrics_summary.csv` into `{slug: float}` for one sample.

    Normalizes `"5,000"` -> 5000.0 and `"92.3%"` -> 0.923 (the fraction unit the
    pack band expects). A missing column omits its slug.
    """
    with open(path, newline="") as fh:
        rows = list(csv.reader(fh))
    if len(rows) < 2:
        return {}
    header, values = rows[0], rows[1]
    out: dict[str, float] = {}
    for label, cell in zip(header, values):
        mapped = _CELLRANGER_FIELD_MAP.get(label.strip().lower())
        if mapped is None:
            continue
        slug, is_percent = mapped
        value = _parse_cellranger_number(cell, is_percent)
        if value is not None:
            out[slug] = value
    return out


# --------------------------------------------------------------------------- #
# simpleaf / alevin-fry — FLOOR ONLY
# --------------------------------------------------------------------------- #


def parse_simpleaf_metrics(path: str | PathLike[str]) -> dict[str, float]:
    """Best-effort simpleaf/alevin-fry cell-QC parser — FLOOR = degrade to `{}`.

    The pinned nf-core/scrnaseq@4.1.0 default (simpleaf) has no confirmed
    machine-readable per-sample cell-QC artifact; it emits AlevinQC/QCatch HTML.
    So any input is UNRECOGNIZED and this returns `{}`, which the caller turns
    into UNVERIFIED — never a false pass. We deliberately do NOT scrape HTML.

    # TODO: if a structured QCatch JSON summary is confirmed against a real
    # fixture, add a recognizer branch here (a clean follow-on, no redesign).
    """
    _ = Path(path)  # accept a path-like; nothing structured to read today
    return {}
