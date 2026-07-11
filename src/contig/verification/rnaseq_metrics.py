"""Parse RSeQC read_distribution.txt into read-composition fractions.

nf-core/rnaseq runs RSeQC `read_distribution` by default and writes
`<sample>.read_distribution.txt`; the exonic/intronic breakdown does NOT reach
Contig's MultiQC general-stats ingest, so this parses the artifact directly.
Local, deterministic, stdlib-only, omit-never-guess.

Denominators (intentional — do NOT change without re-reading the plan):
- `exonic_fraction` / `intronic_fraction` are shares OF **Total Assigned
  Tags** (not Total Tags). RSeQC's `Group` table also reports nested
  `TSS_up_*kb` / `TES_down_*kb` windows; those are promoter/downstream
  windows around the same tags already counted elsewhere in the table and
  are NEVER summed into exonic/intronic — doing so would double-count.
- `unassigned_fraction` is `(Total Tags - Total Assigned Tags) / Total Tags`
  — a DIFFERENT denominator (Total Tags, not Total Assigned Tags), because
  "unassigned" is by definition the tags that never made it into the
  assigned-tags pool in the first place.
"""

from __future__ import annotations

from os import PathLike
from pathlib import Path

EXONIC_FRACTION = "exonic_fraction"
INTRONIC_FRACTION = "intronic_fraction"
UNASSIGNED_FRACTION = "unassigned_fraction"

_EXON_GROUPS = ("CDS_Exons", "5'UTR_Exons", "3'UTR_Exons")
_INTRON_GROUP = "Introns"


def _to_float(text: str) -> float | None:
    """Parse a plain numeric string; return None on anything non-numeric.

    Callers OMIT a slug when this returns None rather than inventing a value.
    """
    try:
        return float(text.strip())
    except (ValueError, AttributeError):
        return None


def _trailing_number(line: str) -> float | None:
    """Extract the last whitespace-delimited token of a preamble line as a
    float, e.g. "Total Assigned Tags   129802" -> 129802.0.
    """
    parts = line.split()
    if not parts:
        return None
    return _to_float(parts[-1])


def parse_read_distribution(path: str | PathLike[str]) -> dict[str, float]:
    """Parse an RSeQC `read_distribution.txt` artifact for ONE sample into
    `{slug: float}` for `exonic_fraction`, `intronic_fraction`,
    `unassigned_fraction`. Any metric whose inputs are absent, non-numeric,
    or whose denominator is zero/negative is OMITTED (never guessed). An
    empty, garbage, or rule-lines-only file returns `{}`.
    """
    total_tags: float | None = None
    assigned: float | None = None
    tag_counts: dict[str, float] = {}

    for raw in Path(path).read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("="):
            continue

        low = line.lower()
        # preamble: "Total Assigned Tags   129802"
        if low.startswith("total assigned tags"):
            assigned = _trailing_number(line)
            continue
        if low.startswith("total tags"):
            total_tags = _trailing_number(line)
            continue
        if low.startswith("total reads"):
            continue

        # table rows: "CDS_Exons   146030   129779   888.71"
        parts = line.split()
        if len(parts) >= 3 and parts[0] in (*_EXON_GROUPS, _INTRON_GROUP):
            val = _to_float(parts[2])  # Tag_count column
            if val is not None:
                tag_counts[parts[0]] = val

    out: dict[str, float] = {}

    # exonic / intronic share OF ASSIGNED TAGS (intentional; do NOT switch to
    # Total Tags — see module docstring).
    if assigned is not None and assigned > 0:
        exon_present = [tag_counts[g] for g in _EXON_GROUPS if g in tag_counts]
        if exon_present:
            out[EXONIC_FRACTION] = sum(exon_present) / assigned
        if _INTRON_GROUP in tag_counts:
            out[INTRONIC_FRACTION] = tag_counts[_INTRON_GROUP] / assigned

    # unassigned share OF ALL TAGS (intentional different denominator — see
    # module docstring).
    if total_tags is not None and total_tags > 0 and assigned is not None:
        unassigned = total_tags - assigned
        if unassigned >= 0:
            out[UNASSIGNED_FRACTION] = unassigned / total_tags

    return out
