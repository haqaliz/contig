"""Detector eval history: the accuracy-over-time trend (moat #2; PRD contract D).

A committed JSONL of EvalSnapshots, one per `eval-detector --snapshot` and one
per successful corpus-promote. Each snapshot is tied to the corpus version it
scored (corpus_sha), so a change in accuracy is always attributable to a change
in either the detector or the corpus.
"""

from __future__ import annotations

from os import PathLike
from pathlib import Path

from contig.models import DetectorEvalReport, EvalSnapshot


def default_history_path() -> Path:
    """Path to the committed history shipped with the package."""
    return Path(__file__).parent / "data" / "eval_history.jsonl"


def snapshot_from_report(
    report: DetectorEvalReport,
    *,
    timestamp: str,
    corpus_size: int,
    corpus_sha: str,
    contig_version: str | None,
) -> EvalSnapshot:
    """Build an EvalSnapshot from an eval report plus the corpus identity.

    The timestamp and corpus_sha are passed in (computed by the caller) so this
    stays a pure projection of the report.
    """
    return EvalSnapshot(
        timestamp=timestamp,
        corpus_size=corpus_size,
        corpus_sha=corpus_sha,
        accuracy=report.accuracy,
        per_class=report.per_class,
        contig_version=contig_version,
    )


def append_snapshot(snapshot: EvalSnapshot, path: str | PathLike[str]) -> None:
    """Append one EvalSnapshot as a JSONL line (creates the file/dirs if needed)."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a") as fh:
        fh.write(snapshot.model_dump_json() + "\n")


def load_history(path: str | PathLike[str]) -> list[EvalSnapshot]:
    """Read the JSONL history into EvalSnapshots; a missing file is empty history."""
    p = Path(path)
    if not p.exists():
        return []
    return [
        EvalSnapshot.model_validate_json(line)
        for line in p.read_text().splitlines()
        if line.strip()
    ]
