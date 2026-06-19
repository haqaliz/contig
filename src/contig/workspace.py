"""Locating run bundles inside a runs directory (ARCHITECTURE §7).

A "runs directory" holds one subdirectory per run, named by its ``run_id``; a
run is considered bundled once that subdir contains a ``run_record.json``. This
module is the single place that maps run_ids to on-disk bundle locations and
loads them back through ``contig.bundle``.
"""

from __future__ import annotations

from pathlib import Path

from contig.bundle import load_bundle
from contig.models import RunRecord


class RunNotFoundError(Exception):
    """Raised when a runs directory has no bundled run for a given run_id."""


def bundle_dir_for(runs_dir: str | Path, run_id: str) -> Path:
    """Return the bundle directory for ``run_id`` under ``runs_dir``."""
    return Path(runs_dir) / run_id


def load_run(runs_dir: str | Path, run_id: str) -> RunRecord:
    """Load the bundled RunRecord for ``run_id`` from ``runs_dir``.

    Raises ``RunNotFoundError`` (not a bare ``FileNotFoundError``) when no
    ``run_record.json`` exists for the run, so callers get a domain error that
    names the run they asked for.
    """
    bundle_dir = bundle_dir_for(runs_dir, run_id)
    if not (bundle_dir / "run_record.json").exists():
        raise RunNotFoundError(f"no bundled run {run_id!r} in {runs_dir}")
    return load_bundle(bundle_dir)


def list_run_ids(runs_dir: str | Path) -> list[str]:
    """Return the sorted run_ids of every bundled run directly under ``runs_dir``.

    A missing (or empty) runs directory simply has no runs, so this returns ``[]``.
    """
    root = Path(runs_dir)
    if not root.is_dir():
        return []
    return sorted(
        child.name
        for child in root.iterdir()
        if (child / "run_record.json").exists()
    )
