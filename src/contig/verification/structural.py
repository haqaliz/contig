"""Structural/integrity QC checks on a run's output files (ARCHITECTURE §6.1).

These are the cheapest verification layer: does the output exist, is it non-empty,
is it indexed, is a gzip stream intact. They run before any content-level QC, since
a missing or truncated file makes deeper checks meaningless.
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from pathlib import Path

from contig.models import QCResult


def check_output(path: str | os.PathLike) -> QCResult:
    """`fail` if the path is missing or zero bytes, else `pass`; value is byte size."""
    p = Path(path)
    if not p.is_file():
        return QCResult(
            check=f"output_present:{p.name}",
            status="fail",
            message="output is missing",
        )
    size = p.stat().st_size
    if size == 0:
        return QCResult(
            check=f"output_present:{p.name}",
            status="fail",
            message="output is empty (0 bytes)",
            value=0.0,
        )
    return QCResult(
        check=f"output_present:{p.name}",
        status="pass",
        message="output present and non-empty",
        value=float(size),
    )


def check_index_present(alignment_path: str | os.PathLike) -> QCResult:
    """`pass` if a sibling index (`.bai` or `.csi`) exists, else `fail`."""
    p = Path(alignment_path)
    has_index = any(
        p.with_name(p.name + suffix).is_file() for suffix in (".bai", ".csi")
    )
    if has_index:
        return QCResult(
            check=f"index_present:{p.name}",
            status="pass",
            message="alignment index present",
        )
    return QCResult(
        check=f"index_present:{p.name}",
        status="fail",
        message="alignment index missing (.bai/.csi)",
    )


_GZIP_MAGIC = b"\x1f\x8b"


def check_gzip_ok(path: str | os.PathLike) -> QCResult:
    """`pass` if the file exists, is non-empty, and starts with gzip magic bytes."""
    p = Path(path)
    if not p.is_file() or p.stat().st_size == 0:
        return QCResult(
            check=f"gzip_ok:{p.name}",
            status="fail",
            message="output is missing or empty",
        )
    with open(p, "rb") as fh:
        header = fh.read(2)
    if header == _GZIP_MAGIC:
        return QCResult(
            check=f"gzip_ok:{p.name}",
            status="pass",
            message="gzip magic bytes present",
        )
    return QCResult(
        check=f"gzip_ok:{p.name}",
        status="fail",
        message="missing gzip magic bytes (truncated or not gzip)",
    )


def evaluate_structural(
    paths: Sequence[str | os.PathLike],
    index_for: Sequence[str | os.PathLike] = (),
) -> list[QCResult]:
    """Run `check_output` on every path and `check_index_present` on `index_for`."""
    results = [check_output(p) for p in paths]
    results.extend(check_index_present(p) for p in index_for)
    return results
