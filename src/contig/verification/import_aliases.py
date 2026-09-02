"""Import-name -> PyPI-package alias table (Phase 1 of reproduce-env-alias-map).

`contig reproduce --allow-install` (C8 env resurrection) installs the detected
missing module token verbatim: `cv2` -> `pip install cv2`, which fails because
the correct PyPI name is `opencv-python`. This module builds a lookup from a
bundled TSV mapping import names to the package names that actually ship them
(`sklearn` -> `scikit-learn`, `PIL` -> `pillow`, `yaml` -> `pyyaml`, ...),
mirroring the `contig_aliases.py` data-table pattern.

It does not get consumed anywhere yet -- this phase is the data table + loud
loader + pure resolver only.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

_DATA_PATH = Path(__file__).parent.parent / "data" / "import_aliases.tsv"


def _build_import_alias_map(lines: Iterable[str]) -> dict[str, str]:
    """Build an import-name -> package-name map from TSV alias rows.

    Tolerant of blank lines and `#`-comment lines, matching the simple
    line-based parsing style used elsewhere in this codebase (e.g.
    `contig_aliases._build_alias_map`). Takes an iterable of lines (not a
    path) so it is unit-testable against synthetic input without touching the
    filesystem; the real bundled TSV is read and passed in by
    `_load_bundled_alias_map` below.

    Fails loud (`ValueError`) rather than silently dropping or
    last-write-wins-overwriting bad data, per this repo's no-silent-failure
    stance:

    - A non-blank, non-comment line that does not split into exactly two
      non-empty tab-separated fields is a malformed row.
    - A key that would end up mapping to two different packages is a
      conflicting duplicate. An exact repeat of an already-seen row is
      harmless (idempotent re-append) and is deduped silently instead of
      erroring -- only a genuine conflict is an error.

    Keys are normalized to lowercase so lookups can stay case-insensitive
    without the table needing per-case rows.
    """
    alias_map: dict[str, str] = {}

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        fields = stripped.split("\t")
        if len(fields) != 2 or not fields[0].strip() or not fields[1].strip():
            raise ValueError(
                f"malformed alias-table row (expected 'import<TAB>package'): {line!r}"
            )

        key = fields[0].strip().lower()
        package = fields[1].strip()
        existing = alias_map.get(key)
        if existing is not None and existing != package:
            raise ValueError(
                f"conflicting alias-table rows: import {key!r} maps to both "
                f"{existing!r} and {package!r}"
            )
        alias_map[key] = package

    return alias_map


def _load_bundled_alias_map(path: Path) -> dict[str, str]:
    """Build the import-name -> package-name map from the bundled TSV."""
    return _build_import_alias_map(path.read_text().splitlines())


_ALIAS_MAP: dict[str, str] = _load_bundled_alias_map(_DATA_PATH)


def package_for_import(name: str) -> str:
    """Return the PyPI package to install for the import `name`.

    Known mismatched imports resolve to their curated package (`cv2` ->
    `opencv-python`); names the table does not cover map to themselves
    verbatim, keeping the honest default byte-identical to today's behavior.
    Lookup normalizes to lowercase (the detector is case-preserving); the
    table's package name is returned verbatim.
    """
    return _ALIAS_MAP.get(name.lower(), name)