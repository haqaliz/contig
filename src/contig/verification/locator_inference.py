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
    and the walk continues into every other directory. A single dirname or
    filename whose `is_symlink()` stat raises (e.g. a delete race) is
    likewise recorded as its own `SweepSkip` in isolation, without dropping
    any of its siblings -- an unreadable subtree, or one flaky entry, must
    never silently shrink the candidate set with no signal (spec R6).

    Returns paths sorted by POSIX-relative path so a sweep is reproducible.
    """
    base = Path(repo)
    if not base.is_dir():
        return [], []
    found: list[Path] = []
    skips: list[SweepSkip] = []

    def _skip_for(bad_path: Path, err: OSError) -> None:
        # An unreadable subtree, or a stat() race on one entry, must never
        # silently shrink the candidate set with no signal -- record it as
        # an honest SweepSkip and let the walk (or this directory's
        # remaining entries) continue (never abort the sweep -- R6).
        try:
            source = bad_path.relative_to(base).as_posix()
        except ValueError:
            source = str(bad_path)
        skips.append(SweepSkip(source=source, reason=str(err)))

    def _walk_onerror(err: OSError) -> None:
        _skip_for(Path(getattr(err, "filename", None) or base), err)

    for dirpath, dirnames, filenames in os.walk(
        base, followlinks=False, onerror=_walk_onerror
    ):
        kept_dirnames = []
        for d in dirnames:
            if d == ".git":
                continue
            dpath = Path(dirpath, d)
            try:
                is_link = dpath.is_symlink()
            except OSError as err:
                # A stat() race on THIS entry only (e.g. it was deleted
                # between os.walk's listdir and our check) must not drop any
                # sibling dirname -- record just this one and keep pruning
                # the rest.
                _skip_for(dpath, err)
                continue
            if not is_link:
                kept_dirnames.append(d)
        dirnames[:] = kept_dirnames

        for name in filenames:
            if not name.endswith(_CANDIDATE_EXTENSIONS):
                continue
            p = Path(dirpath, name)
            try:
                is_link = p.is_symlink()
            except OSError as err:
                # Same isolation for a filename: this entry's failure must
                # not drop any sibling filename in this directory.
                _skip_for(p, err)
                continue
            if is_link:
                continue
            found.append(p)
    return sorted(found, key=lambda p: p.relative_to(base).as_posix()), skips
