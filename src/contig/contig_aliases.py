"""Contig alias equivalence table (Phase 1 of contig-alias-harmonization).

Pre-flight reference-consistency checking (see `reference_check.py`) today
only tolerates a `chr`-prefix mismatch between FASTA and GTF contig naming.
Real references also use per-contig alternate spellings that are not a simple
prefix rule: the mitochondrion is `chrM`/`M` in UCSC-style naming but `MT` in
Ensembl-style naming, and unplaced/unlocalized scaffolds have entirely
different names between the two conventions (e.g. Ensembl `GL000191.1` vs
UCSC `chrUn_GL000191v1`).

This module builds a lookup from any known spelling of a contig to the full
set of equivalent spellings (its "alias group"), merging a code-level
mitochondrion group with a data-driven scaffold table loaded from the bundled
TSV. It does not do any prefix handling itself (that stays in
`reference_check.py` / a later phase) and it does not get consumed anywhere
yet -- this phase is the data table + loader only.
"""

from __future__ import annotations

from pathlib import Path

# Mitochondrion is universal across references (not reference-specific like
# scaffolds), so it is a code constant rather than a TSV row. Bare names only
# -- no `chr` prefix here; prefix handling is a later phase's job.
_MITO: frozenset[str] = frozenset({"M", "MT"})

_DATA_PATH = Path(__file__).parent / "data" / "contig_aliases.tsv"


def _parse_tsv(path: Path) -> list[tuple[str, str]]:
    """Parse the bundled TSV into (ensembl_name, ucsc_name) pairs.

    Tolerant of blank lines and `#`-comment lines, matching the simple
    line-based parsing style used elsewhere in this codebase (e.g.
    `reference_check.gtf_contigs`).
    """
    pairs: list[tuple[str, str]] = []
    text = path.read_text()
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        ensembl, _, ucsc = stripped.partition("\t")
        ensembl = ensembl.strip()
        ucsc = ucsc.strip()
        if ensembl and ucsc:
            pairs.append((ensembl, ucsc))
    return pairs


def _build_alias_map(path: Path) -> dict[str, frozenset[str]]:
    """Build the name -> full-alias-group map from the mito constant + TSV."""
    alias_map: dict[str, frozenset[str]] = {}

    for name in _MITO:
        alias_map[name] = _MITO

    for ensembl, ucsc in _parse_tsv(path):
        group = frozenset({ensembl, ucsc})
        alias_map[ensembl] = group
        alias_map[ucsc] = group

    return alias_map


_ALIAS_MAP: dict[str, frozenset[str]] = _build_alias_map(_DATA_PATH)


def alias_group(name: str) -> frozenset[str]:
    """Return every cross-convention spelling of the contig `name` belongs to.

    Always includes `name` itself. For a name with no known alias (not the
    mitochondrion, not a seeded scaffold), returns `frozenset({name})`.
    """
    group = _ALIAS_MAP.get(name)
    if group is None:
        return frozenset({name})
    return group | {name}
