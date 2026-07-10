"""DADA2 stats parsers for ampliseq metric ingestion.

The ampliseq rule pack (`AMPLISEQ_RULE_PACK`) scores three per-sample
metrics — `percent_retained`, `asv_count`, `input_reads` — but the exact
MultiQC general-stats slug for these is unverified (the source pack docstring
flags it), so the pack silently no-ops on a real nf-core/ampliseq run. These
parsers read DADA2's own on-disk stats artifacts directly.

Structural difference from the methylseq/Bismark parsers this mirrors: DADA2's
`overall_summary.tsv` and ASV table are each a SINGLE file covering MANY
samples (rows or columns keyed by sample), not one file per sample. Both
parsers here therefore return `{sample: {slug: float}}` directly, and the
runner's ampliseq gate merges the two dicts by sample key.

All parsers are pure: they read only the passed file, no network, no
randomness. A metric that is absent or non-numeric is OMITTED (never guessed),
so the gate degrades to UNVERIFIED rather than fabricating a pass.

Coverage:
- `overall_summary.tsv` (DADA2's per-step read-count track table, header row +
  one row per sample): the `input` column -> `input_reads`; `nonchim`
  (post-chimera-removal count) / `input` * 100 -> `percent_retained`, omitted
  when `input` is zero, absent, or non-numeric. Column names are matched
  case-insensitively and a small set of common nf-core/ampliseq naming
  variants is tolerated (e.g. `non-chim`, `nonchimeric`).
- ASV table (`*ASV_table*`, rows=ASVs, columns=samples, integer counts): a
  column is treated as a sample column when every value in it parses as a
  number (a `sequence`/`taxonomy`/id-style metadata column is excluded by
  name and, as a second guard, dropped if any of its values fail to parse as
  a number). `asv_count` = number of ASV rows with a non-zero count in that
  sample's column.
"""

from __future__ import annotations

import csv
from os import PathLike
from pathlib import Path

# Canonical slug names, matching AMPLISEQ_RULE_PACK in rule_pack.py.
INPUT_READS = "input_reads"
PERCENT_RETAINED = "percent_retained"
ASV_COUNT = "asv_count"

_SAMPLE_COLUMN_NAMES = {"sample", "sample_id", "sampleid", "samples", "index"}
_INPUT_COLUMN_NAMES = {"input", "input_reads", "reads_input"}
_NONCHIM_COLUMN_NAMES = {
    "nonchim",
    "non_chim",
    "non-chim",
    "nonchimeric",
    "non_chimeric",
    "non-chimeric",
}
_EXCLUDED_ASV_COLUMNS = {
    "sequence",
    "sequences",
    "asv_id",
    "asv",
    "id",
    "otu",
    "otu_id",
    "taxonomy",
    "#otu id",
}


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
# overall_summary.tsv — header-driven, multi-sample DADA2 track table.
# --------------------------------------------------------------------------- #


def parse_dada2_overall_summary(
    path: str | PathLike[str],
) -> dict[str, dict[str, float]]:
    """Parse DADA2's `overall_summary.tsv` into `{sample: {slug: float}}`.

    `input_reads` comes straight from the input-count column. `percent_retained`
    is `nonchim / input * 100`, omitted when `input` is zero, absent, or
    non-numeric. A file whose header carries neither an input nor a nonchim
    column (i.e. not recognizable as a DADA2 track table at all) is treated as
    unrecognized and returns `{}` rather than guessing a sample column.
    """
    rows = _read_tsv_rows(path)
    if not rows:
        return {}
    header = [cell.strip().lower() for cell in rows[0]]

    input_idx = next((i for i, h in enumerate(header) if h in _INPUT_COLUMN_NAMES), None)
    nonchim_idx = next(
        (i for i, h in enumerate(header) if h in _NONCHIM_COLUMN_NAMES), None
    )
    if input_idx is None and nonchim_idx is None:
        return {}

    sample_idx = next((i for i, h in enumerate(header) if h in _SAMPLE_COLUMN_NAMES), 0)

    out: dict[str, dict[str, float]] = {}
    for row in rows[1:]:
        if sample_idx >= len(row):
            continue
        sample = row[sample_idx].strip()
        if not sample:
            continue
        metrics: dict[str, float] = {}
        input_value = _to_float(row[input_idx]) if input_idx is not None and input_idx < len(row) else None
        nonchim_value = (
            _to_float(row[nonchim_idx]) if nonchim_idx is not None and nonchim_idx < len(row) else None
        )
        if input_value is not None:
            metrics[INPUT_READS] = input_value
        if input_value is not None and input_value != 0 and nonchim_value is not None:
            metrics[PERCENT_RETAINED] = nonchim_value / input_value * 100
        out[sample] = metrics
    return out


# --------------------------------------------------------------------------- #
# ASV table — rows=ASVs, columns=samples, integer counts.
# --------------------------------------------------------------------------- #


def parse_asv_table(path: str | PathLike[str]) -> dict[str, dict[str, float]]:
    """Parse an ASV table (`*ASV_table*`) into `{sample: {asv_count: float}}`.

    Rows are ASVs, columns are samples (plus id/sequence/taxonomy-style
    metadata columns, excluded by name and, as a second guard, dropped if any
    value in the column fails to parse as a number). `asv_count` for a sample
    is the count of ASV rows with a non-zero value in that sample's column.
    No data rows, or no recognizable sample columns, returns `{}`.
    """
    rows = _read_tsv_rows(path)
    if len(rows) < 2:
        return {}
    header = rows[0]
    data_rows = rows[1:]

    candidate_cols = [
        i
        for i, name in enumerate(header)
        if i != 0 and name.strip().lower() not in _EXCLUDED_ASV_COLUMNS
    ]

    sample_cols: list[int] = []
    for i in candidate_cols:
        values = [row[i] if i < len(row) else None for row in data_rows]
        if all(_to_float(v) is not None for v in values):
            sample_cols.append(i)

    if not sample_cols:
        return {}

    out: dict[str, dict[str, float]] = {}
    for i in sample_cols:
        sample = header[i].strip()
        if not sample:
            continue
        count = sum(
            1
            for row in data_rows
            if i < len(row) and (_to_float(row[i]) or 0) != 0
        )
        out[sample] = {ASV_COUNT: float(count)}
    return out
