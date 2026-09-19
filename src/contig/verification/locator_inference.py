"""Safe artifact walk for locator inference (candidate-sweep aspect, R1/R2).

Before a claim's value can be matched to a coordinate in a repo's output
artifacts, we need to know what candidate files exist. `iter_artifacts`
mirrors `bundle.compute_tree_sha256`'s published WALK discipline: prune
`.git` (at any depth) and symlinked directories in place, skip symlinked
files, `os.walk(followlinks=False)`. Only `.json`/`.tsv`/`.csv`/`.tsv.gz`/
`.csv.gz` files are candidates; the result is sorted by POSIX-relative path
for a reproducible sweep.

It deliberately DIVERGES from `compute_tree_sha256` on error handling:
`compute_tree_sha256` produces a single digest, where a partial walk would be
a dishonest result, so any `OSError` aborts it entirely (`onerror=_raise`,
`bundle.py:383-410`). A sweep's contract is the opposite (spec R6): every
unreadable artifact/directory must produce a `SweepSkip` and the sweep must
keep going, never abort. So an unreadable subdirectory here is recorded as a
`SweepSkip` naming it, and the walk continues into the rest of the tree.

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


def iter_artifacts(repo: Path) -> tuple[list[Path], list[SweepSkip]]:
    """Walk `repo` for candidate artifact files, honest and never raising.

    `os.walk(followlinks=False)` with `.git` and symlinked directories
    pruned in place (dirnames mutated) at any depth, and symlinked files
    skipped. Only files ending in `.json`, `.tsv`, `.csv`, `.tsv.gz`, or
    `.csv.gz` are candidates. A missing or non-directory `repo` returns
    `([], [])` rather than raising -- that's an invalid call, not a sweep
    that hit an unreadable directory, so no `SweepSkip` is manufactured for
    it.

    A subdirectory `os.walk` cannot list (e.g. permission denied) is
    recorded as a `SweepSkip(source=<repo-relative posix path>, reason=...)`
    and the walk continues into every other directory -- an unreadable
    subtree must never silently shrink the candidate set with no signal
    (spec R6).

    Returns paths sorted by POSIX-relative path so a sweep is reproducible.
    """
    base = Path(repo)
    if not base.is_dir():
        return [], []
    found: list[Path] = []
    skips: list[SweepSkip] = []

    def _record_skip(err: OSError) -> None:
        # os.walk's default onerror=None would silently skip an unreadable
        # subdirectory and yield fewer entries -- an undisclosed partial
        # sweep. Record it as an honest SweepSkip instead and let the walk
        # continue (never abort the sweep -- R6).
        bad_dir = Path(getattr(err, "filename", None) or base)
        try:
            source = bad_dir.relative_to(base).as_posix()
        except ValueError:
            source = str(bad_dir)
        skips.append(SweepSkip(source=source, reason=str(err)))

    for dirpath, dirnames, filenames in os.walk(
        base, followlinks=False, onerror=_record_skip
    ):
        try:
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
        except OSError as err:
            # A stat() race (e.g. an entry deleted between os.walk's listdir
            # and our is_symlink() check) is the same kind of dishonest
            # silent shrink onerror= exists to prevent -- record it and keep
            # walking rather than raising out of the whole sweep.
            _record_skip(err)
    return sorted(found, key=lambda p: p.relative_to(base).as_posix()), skips
