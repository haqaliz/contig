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

from collections.abc import Iterable
from pathlib import Path

# Mitochondrion is universal across references (not reference-specific like
# scaffolds), so it is a code constant rather than a TSV row. Bare names only
# -- no `chr` prefix here; prefix handling is a later phase's job.
_MITO: frozenset[str] = frozenset({"M", "MT"})

_DATA_PATH = Path(__file__).parent / "data" / "contig_aliases.tsv"


def _build_alias_map(lines: Iterable[str]) -> dict[str, frozenset[str]]:
    """Build a name -> alias-group map from TSV-style alias rows.

    Tolerant of blank lines and `#`-comment lines, matching the simple
    line-based parsing style used elsewhere in this codebase (e.g.
    `reference_check.gtf_contigs`). Takes an iterable of lines (not a path)
    so it is unit-testable against synthetic input without touching the
    filesystem; the real bundled TSV is read and passed in by
    `_load_bundled_alias_map` below.

    Fails loud (`ValueError`) rather than silently dropping or
    last-write-wins-overwriting bad data, per this repo's no-silent-failure
    stance:

    - A non-blank, non-comment line that does not split into exactly two
      non-empty tab-separated fields is a malformed row.
    - A name that would end up belonging to two different (non-identical)
      alias groups is a conflicting duplicate. An exact repeat of an
      already-seen pair is harmless (idempotent re-append) and is deduped
      silently instead of erroring -- only a genuine conflict is an error,
      so every resulting group stays symmetric.
    """
    alias_map: dict[str, frozenset[str]] = {}
    pairs_seen: set[tuple[str, str]] = set()

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        fields = stripped.split("\t")
        if len(fields) != 2 or not fields[0].strip() or not fields[1].strip():
            raise ValueError(
                f"malformed alias-table row (expected 'name<TAB>name'): {line!r}"
            )

        ensembl, ucsc = fields[0].strip(), fields[1].strip()
        pair = (ensembl, ucsc)
        if pair in pairs_seen:
            continue
        pairs_seen.add(pair)

        group = frozenset({ensembl, ucsc})
        for name in (ensembl, ucsc):
            existing = alias_map.get(name)
            if existing is not None and existing != group:
                raise ValueError(
                    f"alias-table name {name!r} appears in conflicting "
                    f"alias groups: {sorted(existing)!r} vs {sorted(group)!r}"
                )
            alias_map[name] = group

    return alias_map


def _load_bundled_alias_map(path: Path) -> dict[str, frozenset[str]]:
    """Build the full name -> alias-group map: mito constant + bundled TSV."""
    alias_map: dict[str, frozenset[str]] = {name: _MITO for name in _MITO}
    alias_map.update(_build_alias_map(path.read_text().splitlines()))
    return alias_map


_ALIAS_MAP: dict[str, frozenset[str]] = _load_bundled_alias_map(_DATA_PATH)


def alias_group(name: str) -> frozenset[str]:
    """Return every cross-convention spelling of the contig `name` belongs to.

    Always includes `name` itself. For a name with no known alias (not the
    mitochondrion, not a seeded scaffold), returns `frozenset({name})`.
    """
    group = _ALIAS_MAP.get(name)
    if group is None:
        return frozenset({name})
    return group | {name}
