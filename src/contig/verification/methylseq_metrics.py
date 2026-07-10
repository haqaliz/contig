"""Bismark bisulfite-report parsers for methylseq metric ingestion.

The methylseq rule pack (`METHYLSEQ_RULE_PACK`) scores three per-sample
metrics — `percent_aligned`, `percent_duplication`, `percent_bs_conversion` —
but nf-core/methylseq does NOT reliably route them into MultiQC general-stats
under a stable slug (the source pack docstring flags them "slug unverified"),
so the pack silently no-ops on a real run. These parsers read Bismark's own
on-disk report artifacts and return `{slug: float}` for ONE sample, which the
runner's methylseq gate feeds to `evaluate()`.

All parsers are pure: they read only the passed file, no network, no
randomness. A metric that is absent or non-numeric is OMITTED (never guessed),
so the gate degrades to UNVERIFIED rather than fabricating a pass.

Coverage by Bismark report kind:
- Alignment report (`*_PE_report.txt` / `*_SE_report.txt`, written by
  `bismark`): `Mapping efficiency:` -> `percent_aligned`.
- Deduplication report (`*.deduplication_report.txt`, written by
  `deduplicate_bismark`): `... duplicated alignments removed:` (with a
  parenthesized percent) -> `percent_duplication`.
- Splitting/conversion report (written by `bismark_methylation_extractor`):
  `percent_bs_conversion` is extracted ONLY when an explicit conversion/
  control-rate line is present. A standard splitting report reports
  methylation-context percentages only, with no conversion rate — that case
  correctly returns `{}` rather than guessing from an unrelated field.
"""

from __future__ import annotations

import re
from os import PathLike
from pathlib import Path

# Canonical slug names, matching METHYLSEQ_RULE_PACK in rule_pack.py.
PERCENT_ALIGNED = "percent_aligned"
PERCENT_DUPLICATION = "percent_duplication"
PERCENT_BS_CONVERSION = "percent_bs_conversion"


def _to_float(text: str) -> float | None:
    """Parse a plain numeric string; return None on anything non-numeric.

    Callers OMIT a slug when this returns None rather than inventing a value.
    """
    try:
        return float(text.strip())
    except (ValueError, AttributeError):
        return None


def _extract(text: str, pattern: re.Pattern[str]) -> float | None:
    match = pattern.search(text)
    if match is None:
        return None
    return _to_float(match.group(1))


# --------------------------------------------------------------------------- #
# Alignment report — "Mapping efficiency:\t78.90%"
# --------------------------------------------------------------------------- #

_MAPPING_EFFICIENCY_RE = re.compile(
    r"Mapping efficiency:[ \t]*([0-9.]+)[ \t]*%", re.IGNORECASE
)


def parse_bismark_alignment_report(path: str | PathLike[str]) -> dict[str, float]:
    """Parse a Bismark alignment report (`*_PE_report.txt` / `*_SE_report.txt`)
    into `{percent_aligned: float}`. Any missing/non-numeric field omits the
    slug; an unrecognized file returns `{}`.
    """
    text = Path(path).read_text()
    value = _extract(text, _MAPPING_EFFICIENCY_RE)
    return {} if value is None else {PERCENT_ALIGNED: value}


# --------------------------------------------------------------------------- #
# Deduplication report — "... duplicated alignments removed:\t97335 (12.34%)"
# --------------------------------------------------------------------------- #

_DUPLICATED_REMOVED_RE = re.compile(
    r"duplicated alignments removed:[ \t]*[0-9,]+[ \t]*\(([0-9.]+)%\)",
    re.IGNORECASE,
)


def parse_bismark_dedup_report(path: str | PathLike[str]) -> dict[str, float]:
    """Parse a Bismark deduplication report (`*.deduplication_report.txt`)
    into `{percent_duplication: float}`. Any missing/non-numeric field omits
    the slug; an unrecognized file returns `{}`.
    """
    text = Path(path).read_text()
    value = _extract(text, _DUPLICATED_REMOVED_RE)
    return {} if value is None else {PERCENT_DUPLICATION: value}


# --------------------------------------------------------------------------- #
# Conversion / splitting report — conversion rate is emitted ONLY when an
# explicit conversion/control-rate line is present.
# --------------------------------------------------------------------------- #

_CONVERSION_RATE_RE = re.compile(
    r"(?:bisulfite )?conversion rate:[ \t]*([0-9.]+)[ \t]*%", re.IGNORECASE
)


def parse_bismark_conversion_report(path: str | PathLike[str]) -> dict[str, float]:
    """Parse a Bismark splitting/conversion report into
    `{percent_bs_conversion: float}`, but ONLY when a recognizable conversion
    or control-rate line is present. A standard splitting report (methylation-
    context percentages, no conversion line) returns `{}` — the floor
    principle applied at the check level: omitted, never guessed from an
    unrelated field.
    """
    text = Path(path).read_text()
    value = _extract(text, _CONVERSION_RATE_RE)
    return {} if value is None else {PERCENT_BS_CONVERSION: value}
