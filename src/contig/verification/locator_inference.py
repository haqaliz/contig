"""Safe artifact walk for locator inference (candidate-sweep aspect, R1/R2).

Before a claim's value can be matched to a coordinate in a repo's output
artifacts, we need to know what candidate files exist. `iter_artifacts`
mirrors `bundle.compute_tree_sha256`'s published walk discipline: prune
`.git` (at any depth) and symlinked directories in place, skip symlinked
files, never raise. Only `.json`/`.tsv`/`.csv`/`.tsv.gz`/`.csv.gz` files are
candidates; the result is sorted by POSIX-relative path for a reproducible
sweep.

This module is the pure substrate only (R1/R2). Enumerating numeric leaves
inside each artifact (R4/R5), the size bound (R3), and the sweep driver are
later slices of the same aspect.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

_CANDIDATE_EXTENSIONS = (".json", ".tsv", ".csv", ".tsv.gz", ".csv.gz")


@dataclass(frozen=True)
class Candidate:
    source: str  # repo-relative POSIX path == the locator "from"
    kind: str  # "json" | "table"
    value: float
    path: str | None = None  # kind == "json"
    column: str | int | None = None  # kind == "table"
    row: int | None = None  # kind == "table"
    header: bool | None = None  # kind == "table"


@dataclass(frozen=True)
class SweepSkip:
    source: str
    reason: str


def iter_artifacts(repo: Path) -> list[Path]:
    """Walk `repo` for candidate artifact files, honest and never raising.

    `os.walk(followlinks=False)` with `.git` and symlinked directories
    pruned in place (dirnames mutated) at any depth, and symlinked files
    skipped. Only files ending in `.json`, `.tsv`, `.csv`, `.tsv.gz`, or
    `.csv.gz` are candidates. A missing or non-directory `repo` returns an
    empty list rather than raising.

    Returns paths sorted by POSIX-relative path so a sweep is reproducible.
    """
    base = Path(repo)
    if not base.is_dir():
        return []
    found: list[Path] = []
    try:
        for dirpath, dirnames, filenames in os.walk(base, followlinks=False):
            dirnames[:] = [
                d
                for d in dirnames
                if d != ".git" and not Path(dirpath, d).is_symlink()
            ]
            for name in filenames:
                if not name.endswith(_CANDIDATE_EXTENSIONS):
                    continue
                p = Path(dirpath, name)
                if p.is_symlink():
                    continue
                found.append(p)
    except OSError:
        return []
    return sorted(found, key=lambda p: p.relative_to(base).as_posix())
